"""
Runtime directories for the KAMVEX sidecar.

The Rust shell passes every directory through environment variables, so the
sidecar never has to guess where the app lives:

    KAMVEX_DATA_DIR       datasets (SHARD shards + IVF-PQ index + meta.json)
    KAMVEX_MODELS_DIR     GGUF models downloaded or imported by the user
    KAMVEX_BINARIES_DIR   llama.cpp binaries (<dir>/<backend>/llama-server.exe)
    KAMVEX_LLAMA_SERVER   explicit path to a llama-server binary (optional)
    KAMVEX_SIBLINGS_DIR   folder that contains DASA-main/ and SHARD-main/ (dev)

Without them (running `python server.py` by hand) the dev layout next to this
file is used; inside a PyInstaller bundle the per-user app-data folder is used.
`DASA_UI_DATA` is still honoured as a legacy alias of `KAMVEX_DATA_DIR`.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

APP_ID = "com.kamvex.app"

_HERE = Path(__file__).resolve()
FROZEN = bool(getattr(sys, "frozen", False))
# In a PyInstaller bundle the data files live in the extraction dir (`sys._MEIPASS`),
# not next to this source file, so catalogs must be looked up there.
SIDECAR_DIR = Path(getattr(sys, "_MEIPASS", _HERE.parent)) if FROZEN else _HERE.parent


def _env_path(*names: str) -> Path | None:
    for n in names:
        v = os.environ.get(n, "").strip()
        if v:
            return Path(v).expanduser()
    return None


def app_local_data_dir() -> Path:
    """Per-user writable folder. Mirrors Tauri's `app_local_data_dir()` for APP_ID."""
    if sys.platform == "win32":
        base = os.environ.get("LOCALAPPDATA") or str(Path.home() / "AppData" / "Local")
        return Path(base) / APP_ID
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / APP_ID
    base = os.environ.get("XDG_DATA_HOME") or str(Path.home() / ".local" / "share")
    return Path(base) / APP_ID


def _default_root() -> Path:
    """Dev layout: <repo>/sidecar/...; frozen bundle: app-data folder."""
    return app_local_data_dir() if FROZEN else SIDECAR_DIR


def data_dir() -> Path:
    return _env_path("KAMVEX_DATA_DIR", "DASA_UI_DATA") or (
        (app_local_data_dir() / "datasets") if FROZEN else (SIDECAR_DIR / "appdata" / "datasets")
    )


def models_dir() -> Path:
    return _env_path("KAMVEX_MODELS_DIR") or (_default_root() / "models")


def binaries_dir() -> Path:
    # Dev layout keeps the historical <repo>/binarios folder.
    return _env_path("KAMVEX_BINARIES_DIR") or (
        (app_local_data_dir() / "binarios") if FROZEN else (SIDECAR_DIR.parent / "binarios")
    )


def siblings_dir() -> Path | None:
    """Folder holding DASA-main/ and SHARD-main/ (only meaningful in dev)."""
    explicit = _env_path("KAMVEX_SIBLINGS_DIR")
    if explicit:
        return explicit
    if FROZEN:
        return None
    return SIDECAR_DIR.parent.parent


def llama_server_binary() -> Path | None:
    """Locate a llama-server executable usable for embeddings (CPU is enough)."""
    explicit = _env_path("KAMVEX_LLAMA_SERVER")
    if explicit and explicit.is_file():
        return explicit
    exe = "llama-server.exe" if sys.platform == "win32" else "llama-server"
    root = binaries_dir()
    for backend in ("cpu", "vulkan", "cuda"):
        p = root / backend / exe
        if p.is_file():
            return p
    return None


def ensure_dir(p: Path) -> Path:
    p.mkdir(parents=True, exist_ok=True)
    return p
