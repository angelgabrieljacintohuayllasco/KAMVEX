"""
Bring up the real KAMVEX stack for QA / benchmarks without the Tauri shell:

  sidecar (python server.py) + llama-server (CPU or Vulkan) + inference hook,
  and install the given .kamvex bundles.

Usage (from the repo root, inside the venv):
    python scripts/qa/stack.py --model sidecar/models/qwen2.5-1.5b-instruct-q4_k_m.gguf \
        --backend cpu --bundles datasets-out/*.kamvex --home E:/kamvex-qa

Prints a JSON line with the ports; keeps running until Ctrl+C (or --exit-after N seconds).
Other scripts import `Stack` to start/stop programmatically.
"""

from __future__ import annotations

import argparse
import glob
import json
import os
import socket
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
SIDECAR_DIR = REPO / "sidecar"
PY = sys.executable
CREATE_NO_WINDOW = 0x08000000 if sys.platform == "win32" else 0


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def http(method: str, url: str, body: dict | None = None, timeout: float = 600) -> dict | list:
    data = json.dumps(body).encode("utf-8") if body is not None else None
    req = urllib.request.Request(url, data=data, method=method,
                                 headers={"Content-Type": "application/json"} if data else {})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        raw = r.read()
    return json.loads(raw) if raw else {}


def wait_http(url: str, timeout: float) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            urllib.request.urlopen(url, timeout=2)
            return True
        except Exception:  # noqa: BLE001
            time.sleep(0.5)
    return False


class Stack:
    def __init__(self, home: Path, model: Path | None, backend: str = "cpu", ctx: int = 4096,
                 threads: int | None = None, ngl: int | None = None):
        self.home = home
        self.model = model
        self.backend = backend
        self.ctx = ctx
        self.threads = threads
        self.ngl = ngl
        self.sidecar_port = free_port()
        self.llama_port = free_port()
        self.sidecar: subprocess.Popen | None = None
        self.llama: subprocess.Popen | None = None
        self.base = f"http://127.0.0.1:{self.sidecar_port}"

    # ── processes ──
    def start_sidecar(self) -> None:
        for d in ("datasets", "models", "logs"):
            (self.home / d).mkdir(parents=True, exist_ok=True)
        env = dict(os.environ)
        env.update({
            "KAMVEX_DATA_DIR": str(self.home / "datasets"),
            "KAMVEX_MODELS_DIR": str(self.home / "models"),
            "KAMVEX_BINARIES_DIR": str(REPO / "binarios"),
            "KAMVEX_LLAMA_SERVER": str(REPO / "binarios" / "cpu" / "llama-server.exe"),
            "KAMVEX_EMBED_MODEL": str(REPO / "sidecar" / "models" / "embeddings" / "all-MiniLM-L6-v2.F16.gguf"),
            "KAMVEX_LOG_LEVEL": "warning",
            "PYTHONIOENCODING": "utf-8",
        })
        log = open(self.home / "logs" / "sidecar.log", "ab")
        self.sidecar = subprocess.Popen([PY, str(SIDECAR_DIR / "server.py"), "--port", str(self.sidecar_port)],
                                        stdout=log, stderr=log, env=env, creationflags=CREATE_NO_WINDOW)
        if not wait_http(f"{self.base}/health", 90):
            raise RuntimeError("sidecar did not start; see logs/sidecar.log")

    def start_llama(self) -> None:
        if not self.model:
            return
        exe = REPO / "binarios" / self.backend / "llama-server.exe"
        if not exe.exists():
            raise RuntimeError(f"missing {exe}")
        ngl = self.ngl if self.ngl is not None else (999 if self.backend != "cpu" else 0)
        args = [str(exe), "-m", str(self.model), "--port", str(self.llama_port), "--host", "127.0.0.1",
                "-c", str(self.ctx), "-ngl", str(ngl), "--no-webui", "--flash-attn", "on",
                "-ctk", "q8_0", "-ctv", "q8_0"]
        if self.threads:
            args += ["-t", str(self.threads)]
        log = open(self.home / "logs" / "llama-server.log", "ab")
        self.llama = subprocess.Popen(args, stdout=log, stderr=log, cwd=str(exe.parent), creationflags=CREATE_NO_WINDOW)
        if not wait_http(f"http://127.0.0.1:{self.llama_port}/health", 300):
            raise RuntimeError("llama-server did not start; see logs/llama-server.log")
        http("POST", f"{self.base}/inference/connect", {"port": self.llama_port})

    def install_bundles(self, bundles: list[Path]) -> list[str]:
        names = []
        for b in bundles:
            r = http("POST", f"{self.base}/datasets/import", {"path": str(b)})
            names.append(r["name"])
        return names

    def stop(self) -> None:
        for p in (self.llama, self.sidecar):
            if p and p.poll() is None:
                p.kill()
                try:
                    p.wait(timeout=10)
                except Exception:  # noqa: BLE001
                    pass

    def __enter__(self):
        self.start_sidecar()
        self.start_llama()
        return self

    def __exit__(self, *a):
        self.stop()


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--home", default=str(REPO / "qa-home"))
    ap.add_argument("--model", default=None)
    ap.add_argument("--backend", default="cpu", choices=["cpu", "vulkan", "cuda"])
    ap.add_argument("--ctx", type=int, default=4096)
    ap.add_argument("--threads", type=int, default=None)
    ap.add_argument("--ngl", type=int, default=None)
    ap.add_argument("--bundles", nargs="*", default=[])
    ap.add_argument("--exit-after", type=float, default=0)
    args = ap.parse_args()

    bundles = [Path(p) for pat in args.bundles for p in glob.glob(pat)]
    model = Path(args.model).resolve() if args.model else None
    if model and not model.is_file():
        raise SystemExit(f"model not found: {model}")
    st = Stack(Path(args.home).resolve(), model, args.backend, args.ctx, args.threads, args.ngl)
    try:
        st.start_sidecar()
        installed = st.install_bundles(bundles)
        st.start_llama()
        info = {"sidecar": st.base, "llama_port": st.llama_port if st.model else None,
                "datasets": installed, "backend": args.backend, "model": str(model) if model else None}
        print(json.dumps(info), flush=True)
        (Path(args.home) / "stack.json").write_text(json.dumps(info), encoding="utf-8")
        if args.exit_after:
            time.sleep(args.exit_after)
        else:
            while True:
                time.sleep(3600)
    finally:
        st.stop()


if __name__ == "__main__":
    main()
