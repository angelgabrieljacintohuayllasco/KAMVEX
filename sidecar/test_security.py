"""
Input validation and hardening of the sidecar HTTP surface.
"""

from __future__ import annotations

from urllib.parse import quote

import pytest

import server
from conftest import DEMO


@pytest.mark.parametrize("bad", ["../evil", "a/b", "a\\b", "", "   ", "x..y", "ends.", "?", "a" * 65])
def test_safe_name_rejects(bad):
    with pytest.raises(Exception) as exc:
        server.safe_name(bad)
    assert getattr(exc.value, "status_code", None) == 400


@pytest.mark.parametrize("good", ["demo", "Mi dataset 2026", "recetas_v1.2", "a-b"])
def test_safe_name_accepts(good):
    assert server.safe_name(good) == good.strip()


def test_build_with_traversal_name_is_400(sidecar):
    r = sidecar.post("/datasets/build", json={"name": "../evil", "json_path": str(DEMO)})
    assert r.status_code == 400


def test_dataset_endpoints_reject_bad_names(sidecar):
    assert sidecar.post("/chat", json={"dataset": "../x", "query": "hola"}).status_code == 400
    # An encoded slash never reaches the handler (router 404) — either way it is rejected.
    assert sidecar.post("/oregano/" + quote("a/b", safe="")).status_code in (400, 404)
    assert sidecar.post("/oregano/" + quote("..\\b", safe="")).status_code == 400
    assert sidecar.get("/datasets/" + quote("..\\x", safe="") + "/export").status_code == 400
    assert sidecar.delete("/datasets/" + quote("../x", safe="")).status_code in (400, 404)
    assert sidecar.delete("/datasets/" + quote("..\\x", safe="")).status_code == 400
    assert sidecar.post("/datasets/" + quote("x..", safe="") + "/summary").status_code == 400


@pytest.mark.parametrize("payload", [
    {"repo": "user/repo", "file": "../evil.gguf"},
    {"repo": "user/repo", "file": "sub/evil.gguf"},
    {"repo": "user/repo", "file": "evil.exe"},
    {"repo": "../evil", "file": "model.gguf"},
    {"repo": "norepo", "file": "model.gguf"},
    {"repo": "user/repo", "file": ""},
])
def test_download_rejects_bad_names(sidecar, payload):
    r = sidecar.post("/models/hub/download", json=payload)
    assert r.status_code == 400, r.text


def test_delete_model_rejects_bad_names(sidecar):
    assert sidecar.delete("/models/local/" + quote("..\\x.gguf", safe="")).status_code == 400
    assert sidecar.delete("/models/local/notes.txt").status_code == 400


def test_inference_connect_loopback_only(sidecar):
    assert sidecar.post("/inference/connect", json={"host": "8.8.8.8", "port": 80}).status_code == 400
    assert sidecar.post("/inference/connect", json={"host": "127.0.0.1", "port": 70000}).status_code == 422
    r = sidecar.post("/inference/connect", json={"host": "127.0.0.1", "port": 1})
    assert r.status_code == 200 and r.json()["status"] == "connected"
    assert sidecar.post("/inference/disconnect").status_code == 200


def test_cors_is_not_wildcard(monkeypatch):
    assert "*" not in server._cors_origins()
    assert "tauri://localhost" in server._cors_origins()
    monkeypatch.setenv("KAMVEX_CORS_ORIGINS", "http://a.test, http://b.test")
    assert server._cors_origins() == ["http://a.test", "http://b.test"]


def test_sampler_bounds_are_enforced(sidecar):
    r = sidecar.post("/chat", json={"dataset": "demo", "query": "hola", "temperature": 9})
    assert r.status_code == 422
    r = sidecar.post("/chat", json={"dataset": "demo", "query": ""})
    assert r.status_code == 422
