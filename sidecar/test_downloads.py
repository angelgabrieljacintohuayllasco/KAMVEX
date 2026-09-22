"""
Download manager: validation, full download over a local HTTP server, cancel, errors.
"""

from __future__ import annotations

import http.server
import os
import socketserver
import threading
from pathlib import Path

import pytest

from downloads import DownloadState, is_valid_filename, is_valid_hf_repo, run_download


@pytest.mark.parametrize("name,ok", [
    ("model.gguf", True), ("Llama-3.2-1B-Instruct-Q4_K_M.gguf", True),
    ("../x.gguf", False), ("a/b.gguf", False), ("a\\b.gguf", False), ("", False), (".hidden", False),
])
def test_filename_validation(name, ok):
    assert is_valid_filename(name) is ok


@pytest.mark.parametrize("repo,ok", [
    ("Qwen/Qwen2.5-0.5B-Instruct-GGUF", True), ("leliuga/all-MiniLM-L6-v2-GGUF", True),
    ("norepo", False), ("../x/y", False), ("a/b/c", False), ("", False),
])
def test_repo_validation(repo, ok):
    assert is_valid_hf_repo(repo) is ok


@pytest.fixture
def http_dir(tmp_path):
    served = tmp_path / "served"
    served.mkdir()
    (served / "file.bin").write_bytes(os.urandom(1_000_000))

    class Handler(http.server.SimpleHTTPRequestHandler):
        def __init__(self, *a, **kw):
            super().__init__(*a, directory=str(served), **kw)

        def log_message(self, *a):  # silence
            pass

    with socketserver.TCPServer(("127.0.0.1", 0), Handler) as httpd:
        t = threading.Thread(target=httpd.serve_forever, daemon=True)
        t.start()
        try:
            yield f"http://127.0.0.1:{httpd.server_address[1]}", served
        finally:
            httpd.shutdown()


def test_full_download(http_dir, tmp_path):
    base, served = http_dir
    dest = tmp_path / "out" / "file.bin"
    state = DownloadState("id1", "x/y", "file.bin", dest, f"{base}/file.bin")
    run_download(state)
    assert state.status == "done", state.error
    assert dest.exists() and dest.stat().st_size == 1_000_000
    assert not Path(str(dest) + ".part").exists()
    assert state.total == 1_000_000 and state.downloaded == 1_000_000
    last = None
    while not state.q.empty():
        last = state.q.get_nowait()
    assert last["status"] == "done" and last["pct"] == 100.0


def test_cancel_while_paused(http_dir, tmp_path):
    base, _ = http_dir
    dest = tmp_path / "file.bin"
    state = DownloadState("id2", "x/y", "file.bin", dest, f"{base}/file.bin")
    state.pause_ev.clear()          # worker will block after the first chunk
    state.status = "paused"
    t = threading.Thread(target=run_download, args=(state,), daemon=True)
    t.start()
    state.cancel()
    t.join(timeout=10)
    assert not t.is_alive()
    assert state.status == "cancelled"
    assert not dest.exists() and not Path(str(dest) + ".part").exists()


def test_http_error_is_reported(http_dir, tmp_path):
    base, _ = http_dir
    dest = tmp_path / "missing.bin"
    state = DownloadState("id3", "x/y", "missing.bin", dest, f"{base}/missing.bin")
    run_download(state)
    assert state.status == "error"
    assert "HTTP 404" in state.error
    assert not dest.exists()
