"""
LlamaEmbeddingEngine — embeddings through `llama-server --embedding`.

Drop-in replacement for `dasa.agent_a.embeddings.EmbeddingEngine`, which needs
sentence-transformers + torch (~2 GB). The Windows installer cannot ship that,
but it already ships llama.cpp, so the same model (all-MiniLM-L6-v2, converted
to GGUF) is served by a second llama-server process. Same 384-dim normalized
space, so datasets built with either engine stay compatible.

Duck-typed contract used by DASA's RetrievalAgent and KAMVEX's build job:

    encode(text) -> np.ndarray (dim,)            L2-normalized
    encode_batch(texts) -> np.ndarray (N, dim)   L2-normalized
    cosine_similarity_batch(q, corpus) -> np.ndarray

The server process is started lazily on first use and killed at exit.
"""

from __future__ import annotations

import atexit
import json
import os
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

import numpy as np

DEFAULT_REPO = "leliuga/all-MiniLM-L6-v2-GGUF"
DEFAULT_FILE = "all-MiniLM-L6-v2.F16.gguf"
DEFAULT_CTX = 512        # BERT positional limit; sentence-transformers truncates at 256 tokens
MAX_CHARS = 1200         # conservative char cap so no input exceeds the context window
BATCH_SIZE = 32
STARTUP_TIMEOUT_S = 90.0


def free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _creation_flags() -> int:
    # CREATE_NO_WINDOW: never pop a console window on Windows.
    return 0x08000000 if sys.platform == "win32" else 0


def _kill_on_close_job():
    """Windows Job Object that kills every assigned process when its handle closes.

    The sidecar is normally terminated with TerminateProcess (Tauri `child.kill()`),
    which skips `atexit`; a job handle owned by this process is closed by the OS at
    death, so the embedding server can never outlive the sidecar. Returns None off Windows.
    """
    if sys.platform != "win32":
        return None
    import ctypes
    from ctypes import wintypes

    kernel32 = ctypes.windll.kernel32
    job = kernel32.CreateJobObjectW(None, None)
    if not job:
        return None

    class IoCounters(ctypes.Structure):
        _fields_ = [(n, ctypes.c_ulonglong) for n in
                    ("ReadOperationCount", "WriteOperationCount", "OtherOperationCount",
                     "ReadTransferCount", "WriteTransferCount", "OtherTransferCount")]

    class BasicLimit(ctypes.Structure):
        _fields_ = [("PerProcessUserTimeLimit", ctypes.c_longlong),
                    ("PerJobUserTimeLimit", ctypes.c_longlong),
                    ("LimitFlags", wintypes.DWORD),
                    ("MinimumWorkingSetSize", ctypes.c_size_t),
                    ("MaximumWorkingSetSize", ctypes.c_size_t),
                    ("ActiveProcessLimit", wintypes.DWORD),
                    ("Affinity", ctypes.c_size_t),
                    ("PriorityClass", wintypes.DWORD),
                    ("SchedulingClass", wintypes.DWORD)]

    class ExtendedLimit(ctypes.Structure):
        _fields_ = [("BasicLimitInformation", BasicLimit),
                    ("IoInfo", IoCounters),
                    ("ProcessMemoryLimit", ctypes.c_size_t),
                    ("JobMemoryLimit", ctypes.c_size_t),
                    ("PeakProcessMemoryUsed", ctypes.c_size_t),
                    ("PeakJobMemoryUsed", ctypes.c_size_t)]

    JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE = 0x2000
    JobObjectExtendedLimitInformation = 9
    info = ExtendedLimit()
    info.BasicLimitInformation.LimitFlags = JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
    ok = kernel32.SetInformationJobObject(job, JobObjectExtendedLimitInformation,
                                          ctypes.byref(info), ctypes.sizeof(info))
    if not ok:
        kernel32.CloseHandle(job)
        return None
    return job


def _assign_to_job(job, proc: subprocess.Popen) -> bool:
    if job is None or sys.platform != "win32":
        return False
    import ctypes
    handle = ctypes.windll.kernel32.OpenProcess(0x1F0FFF, False, proc.pid)  # PROCESS_ALL_ACCESS
    if not handle:
        return False
    try:
        return bool(ctypes.windll.kernel32.AssignProcessToJobObject(job, handle))
    finally:
        ctypes.windll.kernel32.CloseHandle(handle)


class LlamaEmbeddingEngine:
    """Embeddings served by a private llama-server instance."""

    def __init__(self, server_bin: str | os.PathLike, model_path: str | os.PathLike,
                 ctx: int = DEFAULT_CTX, threads: int | None = None,
                 startup_timeout: float = STARTUP_TIMEOUT_S) -> None:
        self.server_bin = Path(server_bin)
        self.model_path = Path(model_path)
        self.ctx = int(ctx)
        self.threads = threads
        self.startup_timeout = startup_timeout
        self._proc: subprocess.Popen | None = None
        self._port: int | None = None
        self._dim: int | None = None
        self._atexit_registered = False
        self._job = None          # Windows job handle: children die with this process
        self.job_assigned = False

    # ── lifecycle ────────────────────────────────────────────────────────────

    @property
    def running(self) -> bool:
        return self._proc is not None and self._proc.poll() is None

    @property
    def port(self) -> int | None:
        return self._port if self.running else None

    @property
    def dim(self) -> int | None:
        return self._dim

    def describe(self) -> dict:
        return {
            "backend": "llama-gguf",
            "model": self.model_path.name,
            "model_path": str(self.model_path),
            "server_bin": str(self.server_bin),
            "running": self.running,
            "port": self.port,
            "pid": self._proc.pid if self.running else None,
            "dim": self._dim,
            "job_assigned": self.job_assigned,
        }

    def _command(self, port: int) -> list[str]:
        cmd = [
            str(self.server_bin),
            "-m", str(self.model_path),
            "--embedding",
            "--pooling", "mean",
            "--embd-normalize", "2",
            "-c", str(self.ctx),
            "-b", str(self.ctx),
            "-ub", str(self.ctx),
            "-ngl", "0",
            "--host", "127.0.0.1",
            "--port", str(port),
            "--no-webui",
            "--log-disable",
        ]
        if self.threads:
            cmd += ["-t", str(int(self.threads))]
        return cmd

    def start(self) -> None:
        """Spawn llama-server and wait until /health answers. Idempotent."""
        if self.running:
            return
        if not self.server_bin.is_file():
            raise RuntimeError(f"llama-server no encontrado: {self.server_bin}")
        if not self.model_path.is_file():
            raise RuntimeError(f"modelo de embeddings no encontrado: {self.model_path}")

        port = free_port()
        self._proc = subprocess.Popen(
            self._command(port),
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            stdin=subprocess.DEVNULL,
            creationflags=_creation_flags(),
        )
        self._port = port
        if self._job is None:
            self._job = _kill_on_close_job()
        self.job_assigned = _assign_to_job(self._job, self._proc)
        if not self._atexit_registered:
            atexit.register(self.stop)
            self._atexit_registered = True

        deadline = time.time() + self.startup_timeout
        while time.time() < deadline:
            if self._proc.poll() is not None:
                code = self._proc.returncode
                self._proc = None
                raise RuntimeError(
                    f"llama-server (embeddings) terminó con código {code}; "
                    "¿el GGUF es un modelo de embeddings válido?"
                )
            if self._health():
                return
            time.sleep(0.25)
        self.stop()
        raise RuntimeError("llama-server (embeddings) no respondió a tiempo")

    def stop(self) -> None:
        proc, self._proc = self._proc, None
        if proc is None:
            return
        try:
            proc.kill()
            proc.wait(timeout=5)
        except Exception:  # noqa: BLE001 — best effort on shutdown
            pass

    # ── HTTP ────────────────────────────────────────────────────────────────

    def _base(self) -> str:
        return f"http://127.0.0.1:{self._port}"

    def _health(self) -> bool:
        try:
            with urllib.request.urlopen(f"{self._base()}/health", timeout=2) as r:
                return r.status == 200
        except Exception:  # noqa: BLE001
            return False

    def _post_embeddings(self, texts: list[str]) -> list[list[float]]:
        body = json.dumps({"input": texts, "model": "embeddings"}).encode("utf-8")
        req = urllib.request.Request(
            f"{self._base()}/v1/embeddings", data=body,
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=120) as resp:
            data = json.loads(resp.read())
        rows = sorted(data["data"], key=lambda d: d.get("index", 0))
        return [r["embedding"] for r in rows]

    def _embed_chunk(self, texts: list[str]) -> list[list[float]]:
        """Embed a chunk; on a 4xx (input too long) fall back to halving each text."""
        try:
            return self._post_embeddings(texts)
        except urllib.error.HTTPError as e:
            if e.code < 400 or e.code >= 500 or all(len(t) <= 64 for t in texts):
                raise RuntimeError(f"llama-server embeddings HTTP {e.code}") from e
            shorter = [t[: max(32, len(t) // 2)] for t in texts]
            return self._embed_chunk(shorter)

    # ── EmbeddingEngine contract ────────────────────────────────────────────

    @staticmethod
    def _prepare(text) -> str:
        t = str(text).strip()
        if not t:
            t = " "
        return t[:MAX_CHARS]

    def encode_batch(self, texts) -> np.ndarray:
        self.start()
        texts = [self._prepare(t) for t in texts]
        if not texts:
            return np.zeros((0, self._dim or 0), dtype=np.float32)
        out: list[list[float]] = []
        for i in range(0, len(texts), BATCH_SIZE):
            out.extend(self._embed_chunk(texts[i:i + BATCH_SIZE]))
        arr = np.asarray(out, dtype=np.float32)
        norms = np.linalg.norm(arr, axis=1, keepdims=True)
        norms[norms == 0] = 1.0
        arr = arr / norms
        self._dim = int(arr.shape[1])
        return arr

    def encode(self, text) -> np.ndarray:
        return self.encode_batch([text])[0]

    @staticmethod
    def cosine_similarity_batch(query_vec: np.ndarray, corpus_vecs: np.ndarray) -> np.ndarray:
        return np.dot(corpus_vecs, query_vec)
