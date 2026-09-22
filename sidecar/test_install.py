"""
Dataset bundles: catalog, install from URL (download → sha256 → unpack), local import,
rebuild from bundled records, and rejection of unsafe bundles / URLs.
"""

from __future__ import annotations

import http.server
import io
import json
import socketserver
import threading
import zipfile
from pathlib import Path

import pytest

import server
from conftest import build_dataset, demo_records, sse_stages
from downloads import is_allowed_url, sha256_file
from jobs import record_to_text

pytestmark = pytest.mark.skipif(not server._DASA_AVAILABLE, reason="DASA/SHARD not importable")


def _events(client, dl_id: str) -> list[dict]:
    text = client.get(f"/downloads/{dl_id}/events").text
    return [json.loads(l[6:]) for l in text.splitlines() if l.startswith("data: ")]


@pytest.fixture
def served(tmp_path):
    root = tmp_path / "www"
    root.mkdir()

    class Handler(http.server.SimpleHTTPRequestHandler):
        def __init__(self, *a, **kw):
            super().__init__(*a, directory=str(root), **kw)

        def log_message(self, *a):
            pass

    with socketserver.TCPServer(("127.0.0.1", 0), Handler) as httpd:
        threading.Thread(target=httpd.serve_forever, daemon=True).start()
        try:
            yield root, f"http://127.0.0.1:{httpd.server_address[1]}"
        finally:
            httpd.shutdown()


def _export_bundle(client, name: str) -> bytes:
    r = client.get(f"/datasets/{name}/export")
    assert r.status_code == 200
    return r.content


def test_url_allowlist(monkeypatch):
    assert is_allowed_url("https://github.com/x/y/releases/download/v1/a.kamvex")
    assert is_allowed_url("https://huggingface.co/x/y/resolve/main/a.kamvex")
    assert not is_allowed_url("http://github.com/x")           # plain http
    assert not is_allowed_url("https://evil.example/a.kamvex")
    assert not is_allowed_url("https://127.0.0.1:8000/a")
    monkeypatch.setenv("KAMVEX_ALLOWED_HOSTS", "mirror.example")
    assert is_allowed_url("https://mirror.example/a.kamvex")


def test_install_from_url_with_sha256(sidecar, served, monkeypatch):
    root, base = served
    monkeypatch.setenv("KAMVEX_ALLOWED_HOSTS", "127.0.0.1")
    build_dataset(sidecar, "demo")
    bundle = root / "demo.kamvex"
    bundle.write_bytes(_export_bundle(sidecar, "demo"))
    sha = sha256_file(bundle)

    r = sidecar.post("/datasets/install", json={"url": f"{base}/demo.kamvex", "name": "demo copia", "sha256": sha})
    assert r.status_code == 200, r.text
    dl = r.json()["download_id"]
    evs = _events(sidecar, dl)
    statuses = [e["status"] for e in evs]
    assert statuses[-1] == "done", evs
    assert "verifying" in statuses and "installing" in statuses
    assert evs[-1]["result"]["n_records"] == len(demo_records())

    names = [d["name"] for d in sidecar.get("/datasets").json()]
    assert "demo copia" in names
    q = record_to_text(demo_records()[0])
    resp = sidecar.post("/chat", json={"dataset": "demo copia", "query": q}).json()
    assert resp["fragments"]
    assert not (server.DATA_DIR / "_downloads" / "demo copia.kamvex").exists(), "bundle removed after install"


def test_install_sha256_mismatch_is_reported(sidecar, served, monkeypatch):
    root, base = served
    monkeypatch.setenv("KAMVEX_ALLOWED_HOSTS", "127.0.0.1")
    build_dataset(sidecar, "demo")
    (root / "demo.kamvex").write_bytes(_export_bundle(sidecar, "demo"))
    r = sidecar.post("/datasets/install", json={"url": f"{base}/demo.kamvex", "name": "bad", "sha256": "00" * 32})
    evs = _events(sidecar, r.json()["download_id"])
    assert evs[-1]["status"] == "error"
    assert "sha256" in evs[-1]["error"]
    assert all(d["name"] != "bad" for d in sidecar.get("/datasets").json())


def test_install_rejects_bad_urls_and_names(sidecar):
    assert sidecar.post("/datasets/install", json={"url": "https://evil.example/x.kamvex", "name": "x"}).status_code == 400
    assert sidecar.post("/datasets/install", json={"url": "https://github.com/a/b/x.kamvex", "name": "../x"}).status_code == 400
    assert sidecar.post("/datasets/install", json={"id": "does-not-exist"}).status_code == 404


def test_import_local_bundle_and_rebuild(sidecar, tmp_path):
    build_dataset(sidecar, "demo")
    bundle = tmp_path / "exportado.kamvex"
    bundle.write_bytes(_export_bundle(sidecar, "demo"))
    r = sidecar.post("/datasets/import", json={"path": str(bundle)})
    assert r.status_code == 200, r.text
    assert r.json()["name"] == "exportado"
    assert (server.DATA_DIR / "exportado" / "meta.json").exists()

    # exported demo has no records.json → rebuild refused
    assert sidecar.post("/datasets/exportado/rebuild", json={}).status_code == 404

    # a text dataset keeps records.json → rebuild works
    r = sidecar.post("/datasets/build-text", json={"name": "texto", "text": "Uno dos tres.\nCuatro cinco seis.\n" * 20})
    assert r.status_code == 200
    assert "done" in sse_stages(sidecar.get(f"/datasets/build/{r.json()['job_id']}/events").text)
    r = sidecar.post("/datasets/texto/rebuild", json={"profile": "low-ram"})
    assert r.status_code == 200, r.text
    assert "done" in sse_stages(sidecar.get(f"/datasets/build/{r.json()['job_id']}/events").text)
    assert sidecar.post("/datasets/nope/rebuild", json={}).status_code == 404


def test_import_rejects_zip_slip_and_missing_meta(sidecar, tmp_path):
    evil = tmp_path / "evil.kamvex"
    with zipfile.ZipFile(evil, "w") as zf:
        zf.writestr("meta.json", json.dumps({"n_records": 1, "num_shards": 1}))
        zf.writestr("../../pwned.txt", "x")
    assert sidecar.post("/datasets/import", json={"path": str(evil)}).status_code == 400

    nometa = tmp_path / "nometa.kamvex"
    with zipfile.ZipFile(nometa, "w") as zf:
        zf.writestr("shard_000000.bin", b"\0")
    assert sidecar.post("/datasets/import", json={"path": str(nometa)}).status_code == 400
    assert sidecar.post("/datasets/import", json={"path": str(tmp_path / "missing.kamvex")}).status_code == 404


def test_catalog_marks_installed(sidecar, monkeypatch, tmp_path):
    cat = tmp_path / "catalog.json"
    cat.write_text(json.dumps({
        "version": 1,
        "release_base": "https://github.com/owner/repo/releases/download/datasets-v1",
        "datasets": [
            {"id": "demo", "name": "Demo", "file": "demo.kamvex", "sha256": "ab" * 32, "records": 10},
            {"id": "otro", "name": "Otro", "file": "otro.kamvex", "records": 5},
        ],
    }), encoding="utf-8")
    monkeypatch.setattr(server, "DATASET_CATALOG_FILE", cat)
    monkeypatch.setattr(server, "_CATALOG_CACHE", {"at": 0.0, "data": None})
    build_dataset(sidecar, "demo")
    data = sidecar.get("/datasets/catalog").json()
    by_id = {d["id"]: d for d in data["datasets"]}
    assert by_id["demo"]["installed"] is True
    assert by_id["otro"]["installed"] is False
    assert by_id["otro"]["url"].endswith("/datasets-v1/otro.kamvex")
