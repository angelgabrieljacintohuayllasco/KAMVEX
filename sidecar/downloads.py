"""
Background file downloads with pause / resume / cancel and SSE-friendly progress.

Used for GGUF models pulled from HuggingFace and for the embedding model the
sidecar needs when sentence-transformers is not installed (installer builds).

Design:
- One `DownloadState` per download, kept in memory (a sidecar restart forgets
  active downloads; the `.part` file on disk still allows resuming later).
- The worker thread streams 256 KB chunks into `<dest>.part`, honours
  `pause_ev` / `cancel_ev`, and resumes with an HTTP Range request when a
  `.part` file already exists.
- Progress events are pushed to `state.q`; the HTTP layer drains that queue
  into a Server-Sent Events stream.
"""

from __future__ import annotations

import hashlib
import os
import queue
import re
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from pathlib import Path
from typing import Callable

CHUNK_SIZE = 256 * 1024
EMIT_EVERY_S = 0.5
FINAL_STATES = ("done", "error", "cancelled")
# Hosts KAMVEX downloads from (models: HuggingFace; datasets: GitHub Releases / HF).
ALLOWED_HOSTS = ("huggingface.co", "github.com", "objects.githubusercontent.com",
                 "release-assets.githubusercontent.com", "raw.githubusercontent.com")

_HF_REPO_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,95}/[A-Za-z0-9][A-Za-z0-9._-]{0,95}$")
_FILENAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,254}$")


def is_valid_hf_repo(repo: str) -> bool:
    return bool(_HF_REPO_RE.match(repo or ""))


def is_allowed_url(url: str, extra_hosts: tuple[str, ...] = ()) -> bool:
    """https only, host on the allowlist (env KAMVEX_ALLOWED_HOSTS adds more, comma separated)."""
    try:
        u = urllib.parse.urlparse(url)
    except ValueError:
        return False
    if not u.hostname:
        return False
    env_hosts = tuple(h.strip().lower() for h in os.environ.get("KAMVEX_ALLOWED_HOSTS", "").split(",") if h.strip())
    host = u.hostname.lower()
    if u.scheme == "http":
        # Plain http only for an explicitly whitelisted loopback mirror (tests, local dev).
        return host in ("127.0.0.1", "localhost") and host in env_hosts
    if u.scheme != "https":
        return False
    return host in ALLOWED_HOSTS or host in extra_hosts or host in env_hosts


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def is_valid_filename(name: str) -> bool:
    """A single path component: no separators, no traversal, sane characters."""
    if not name or ".." in name or "/" in name or "\\" in name:
        return False
    return bool(_FILENAME_RE.match(name))


def hf_resolve_url(repo: str, file: str) -> str:
    return f"https://huggingface.co/{repo}/resolve/main/{file}"


class DownloadState:
    """Tracks a single download with pause/cancel support."""

    __slots__ = ("id", "repo", "file", "dest", "url", "total", "downloaded",
                 "speed", "status", "error", "cancel_ev", "pause_ev", "q", "thread",
                 "kind", "expected_sha256", "post_process", "result")

    def __init__(self, dl_id: str, repo: str, file: str, dest: Path, url: str, *,
                 kind: str = "model", expected_sha256: str | None = None,
                 post_process: "Callable[[DownloadState], dict | None] | None" = None):
        self.id = dl_id
        self.repo = repo
        self.file = file
        self.dest = dest
        self.url = url
        self.total: int = 0
        self.downloaded: int = 0
        self.speed: float = 0.0
        # downloading | paused | verifying | installing | done | error | cancelled
        self.status: str = "downloading"
        self.error: str = ""
        self.cancel_ev = threading.Event()
        self.pause_ev = threading.Event()  # SET = running, CLEAR = paused
        self.pause_ev.set()
        self.q: queue.Queue = queue.Queue()
        self.thread: threading.Thread | None = None
        self.kind = kind
        self.expected_sha256 = (expected_sha256 or "").lower().strip() or None
        self.post_process = post_process
        self.result: dict | None = None

    @property
    def active(self) -> bool:
        return self.status in ("downloading", "paused", "verifying", "installing")

    def progress_pct(self) -> float:
        if self.total <= 0:
            return 0.0
        return round(self.downloaded / self.total * 100, 1)

    def snapshot(self) -> dict:
        return {
            "status": self.status,
            "downloaded": self.downloaded,
            "total": self.total,
            "pct": self.progress_pct(),
            "speed_mbps": round(self.speed, 2),
            "error": self.error,
            "file": self.file,
            "kind": self.kind,
            "result": self.result,
        }

    def emit(self) -> None:
        self.q.put(self.snapshot())

    def pause(self) -> None:
        if self.status == "downloading":
            self.pause_ev.clear()
            self.status = "paused"
            self.emit()

    def resume(self) -> None:
        if self.status == "paused":
            self.status = "downloading"
            self.pause_ev.set()
            self.emit()

    def cancel(self) -> None:
        self.cancel_ev.set()
        self.pause_ev.set()


def _request_headers(resume_from: int) -> dict:
    headers = {"User-Agent": "KAMVEX/0.1 (+https://github.com/angelgabrieljacintohuayllasco/KAMVEX)"}
    token = os.environ.get("HF_TOKEN", "").strip()
    if token:
        headers["Authorization"] = f"Bearer {token}"
    if resume_from > 0:
        headers["Range"] = f"bytes={resume_from}-"
    return headers


class DiskSpaceError(OSError):
    """No cabe. Se avisa antes de empezar, no a mitad de una descarga de 40 GB."""


# Margen que se deja libre después de la descarga. Llenar el disco al 100 % rompe cosas
# que no tienen nada que ver con KAMVEX. El margen es proporcional: uno fijo y grande
# impediría bajar 60 MB en un disco con 1 GB libre, que es perfectamente razonable.
DISK_MARGIN_MIN = 200_000_000
DISK_MARGIN_MAX = 2_000_000_000
DISK_MARGIN_SHARE = 0.10


def disk_margin(needed: int) -> int:
    """Cuánto hay que dejar libre además del propio fichero."""
    return int(min(DISK_MARGIN_MAX, max(DISK_MARGIN_MIN, needed * DISK_MARGIN_SHARE)))


def free_space(path: Path) -> int:
    """Bytes libres en el disco donde caería `path`, o -1 si no se puede saber."""
    import shutil
    carpeta = path if path.is_dir() else path.parent
    while not carpeta.exists() and carpeta != carpeta.parent:
        carpeta = carpeta.parent
    try:
        return shutil.disk_usage(carpeta).free
    except OSError:
        return -1


def remote_size(url: str, timeout: float = 20.0) -> int:
    """Lo que pesa el fichero según el servidor, o 0 si no lo dice.

    Hugging Face manda el tamaño real en `x-linked-size` cuando el fichero vive en LFS;
    `Content-Length` en ese caso es el del puntero, que son unos cientos de bytes.
    """
    try:
        req = urllib.request.Request(url, headers=_request_headers(0), method="HEAD")
        with urllib.request.urlopen(req, timeout=timeout) as r:
            for cabecera in ("x-linked-size", "Content-Length"):
                valor = r.headers.get(cabecera)
                if valor and valor.isdigit() and int(valor) > 0:
                    return int(valor)
    except Exception:  # noqa: BLE001 — sin dato se sigue y se comprueba al vuelo
        return 0
    return 0


def check_space(dest: Path, needed: int) -> str | None:
    """Mensaje de error si no cabe, o None si hay sitio.

    Se comprueba ANTES de empezar: enterarse al 90 % de una descarga de 40 GB, con el
    disco ya lleno y el sistema dando problemas, no le sirve a nadie.
    """
    if needed <= 0:
        return None
    libre = free_space(dest)
    if libre < 0:
        return None
    if libre < needed + disk_margin(needed):
        return (f"No hay espacio suficiente: el archivo ocupa {needed / 1e9:.1f} GB y en el "
                f"disco quedan {libre / 1e9:.1f} GB. Libera espacio o elige un modelo más "
                f"pequeño.")
    return None


def run_download(state: DownloadState) -> None:
    """Worker: chunked download with pause/cancel/resume. Never raises."""
    part = Path(str(state.dest) + ".part")
    resume_from = part.stat().st_size if part.exists() else 0

    try:
        part.parent.mkdir(parents=True, exist_ok=True)
        req = urllib.request.Request(state.url, headers=_request_headers(resume_from))
        resp = urllib.request.urlopen(req, timeout=30)

        content_length = resp.headers.get("Content-Length")
        resumed = resume_from > 0 and resp.status == 206
        if resumed:
            state.downloaded = resume_from
            content_range = resp.headers.get("Content-Range", "")
            if "/" in content_range and content_range.split("/")[-1].isdigit():
                state.total = int(content_range.split("/")[-1])
            elif content_length:
                state.total = resume_from + int(content_length)
        else:
            # Server ignored the Range header (or nothing to resume): start over.
            state.downloaded = 0
            state.total = int(content_length) if content_length else 0

        falta = check_space(state.dest, state.total - state.downloaded)
        if falta:
            state.status = "error"
            state.error = falta
            state.emit()
            resp.close()
            return

        state.emit()

        last_time = time.time()
        last_bytes = state.downloaded

        with open(part, "ab" if resumed else "wb") as f:
            while True:
                if state.cancel_ev.is_set():
                    state.status = "cancelled"
                    state.emit()
                    f.close()
                    part.unlink(missing_ok=True)
                    return

                state.pause_ev.wait()
                if state.cancel_ev.is_set():
                    continue

                data = resp.read(CHUNK_SIZE)
                if not data:
                    break

                f.write(data)
                state.downloaded += len(data)

                now = time.time()
                elapsed = now - last_time
                if elapsed >= EMIT_EVERY_S:
                    state.speed = (state.downloaded - last_bytes) / elapsed / 1_000_000
                    last_time = now
                    last_bytes = state.downloaded
                    state.emit()

        if state.total and state.downloaded != state.total:
            raise IOError(
                f"descarga incompleta: {state.downloaded} de {state.total} bytes "
                "(reintenta para reanudar)"
            )

        state.dest.parent.mkdir(parents=True, exist_ok=True)
        os.replace(part, state.dest)
        state.speed = 0.0

        if state.expected_sha256:
            state.status = "verifying"
            state.emit()
            actual = sha256_file(state.dest)
            if actual != state.expected_sha256:
                state.dest.unlink(missing_ok=True)
                raise IOError(f"sha256 no coincide (esperado {state.expected_sha256[:12]}…, obtenido {actual[:12]}…)")

        if state.post_process is not None:
            state.status = "installing"
            state.emit()
            state.result = state.post_process(state)

        state.status = "done"
        state.emit()

    except urllib.error.HTTPError as e:
        state.status = "error"
        state.error = f"HTTP {e.code} al descargar {state.file}"
        if e.code in (401, 403):
            state.error += " (repositorio privado o con acceso restringido; define HF_TOKEN)"
        state.emit()
    except Exception as e:  # noqa: BLE001 — surface any failure to the UI
        state.status = "error"
        state.error = str(e)
        state.emit()


class DownloadManager:
    """Registry of downloads keyed by id. Thread-safe for the sidecar's needs."""

    def __init__(self) -> None:
        self._items: dict[str, DownloadState] = {}
        self._lock = threading.Lock()

    def get(self, dl_id: str) -> DownloadState | None:
        return self._items.get(dl_id)

    def active_for(self, dest: Path) -> DownloadState | None:
        with self._lock:
            for dl in self._items.values():
                if dl.dest == dest and dl.active:
                    return dl
        return None

    def start(self, repo: str, file: str, dest: Path, *, url: str | None = None,
              kind: str = "model", sha256: str | None = None,
              post_process: "Callable[[DownloadState], dict | None] | None" = None) -> DownloadState:
        """Start (or return the already running) download into dest.

        `url` defaults to the HuggingFace resolve URL for repo/file. `sha256` is
        verified after the download; `post_process` runs before the final "done"
        (used to unpack dataset bundles) and its return value lands in `result`.
        """
        existing = self.active_for(dest)
        if existing is not None:
            return existing
        # Se pregunta el tamaño y se comprueba el disco ANTES de arrancar el hilo.
        destino_url = url or hf_resolve_url(repo, file)
        falta = check_space(dest, remote_size(destino_url))
        if falta:
            raise DiskSpaceError(falta)
        dl_id = uuid.uuid4().hex[:12]
        state = DownloadState(dl_id, repo, file, dest, url or hf_resolve_url(repo, file),
                              kind=kind, expected_sha256=sha256, post_process=post_process)
        with self._lock:
            self._items[dl_id] = state
        t = threading.Thread(target=run_download, args=(state,), daemon=True,
                             name=f"download-{dl_id}")
        state.thread = t
        t.start()
        return state

    def snapshot(self) -> list[dict]:
        with self._lock:
            return [{"download_id": k, **v.snapshot()} for k, v in self._items.items()]
