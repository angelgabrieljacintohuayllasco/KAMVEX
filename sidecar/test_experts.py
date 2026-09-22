"""
Experts: catalog shape, readiness on this machine, and chat routing
(corpus-less experts talk to the LLM; corpus experts search their datasets,
apply their mode, prompt and samplers).
"""

from __future__ import annotations

import json

import pytest

import experts as experts_mod
import server
from conftest import FakeConnector, build_dataset, demo_records
from jobs import record_to_text


def test_catalog_loads_and_is_consistent():
    catalog = experts_mod.load_catalog()
    assert len(catalog) >= 5
    ids = [e.id for e in catalog]
    assert len(ids) == len(set(ids))
    for e in catalog:
        assert e.name and e.description
        assert e.default_mode in experts_mod.MODES
        assert e.examples, f"{e.id} has no example questions"
        if e.default_mode != "free":
            assert e.datasets or e.id == "general"
        for m in e.models:
            assert m.file.endswith(".gguf") and m.repo


def test_catalog_missing_file_is_empty(tmp_path):
    assert experts_mod.load_catalog(tmp_path / "nope.json") == []
    bad = tmp_path / "bad.json"
    bad.write_text("{not json", encoding="utf-8")
    assert experts_mod.load_catalog(bad) == []


def test_status_reports_what_is_missing():
    e = experts_mod.Expert.from_json({
        "id": "x", "name": "X", "datasets": ["a", "b"], "default_mode": "grounded",
        "models": [{"id": "m1", "name": "M1", "repo": "r/m", "file": "m1.gguf"}],
    })
    st = experts_mod.status(e, installed_datasets={"a"}, local_model_files=set())
    assert st["ready"] is False and st["missing_datasets"] == ["b"] and st["model_present"] is None
    st = experts_mod.status(e, installed_datasets={"a", "b"}, local_model_files={"m1.gguf"})
    assert st["ready"] is True and st["model_present"] == "m1"
    # statistical experts do not need a model
    s = experts_mod.Expert.from_json({"id": "s", "name": "S", "datasets": ["a"], "default_mode": "statistical"})
    assert experts_mod.status(s, {"a"}, set())["ready"] is True


def test_experts_endpoint_marks_installed(sidecar):
    data = sidecar.get("/experts").json()
    assert data["experts"], data
    by_id = {e["id"]: e for e in data["experts"]}
    assert "programacion" in by_id and "salud" in by_id
    prog = by_id["programacion"]
    assert prog["status"]["ready"] is False
    assert "python-docs-es" in prog["status"]["missing_datasets"]
    assert prog["models"][0]["id"].startswith("qwen2.5-coder")
    assert sidecar.get("/experts/salud").status_code == 200
    assert sidecar.get("/experts/nope").status_code == 404


def test_expert_chat_without_corpus_uses_prompt_and_samplers(sidecar, monkeypatch):
    conn = FakeConnector(reply="respuesta general")
    monkeypatch.setattr(server, "_LLAMA_CONNECTOR", conn)
    r = sidecar.post("/experts/general/chat", json={"expert": "general", "query": "hola",
                                                    "history": [{"role": "user", "content": "previo"},
                                                                {"role": "assistant", "content": "ok"}]})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["answer"] == "respuesta general" and body["meta"]["corpus"] is False
    msgs = conn.calls[0]
    assert msgs[0]["role"] == "system" and "KAMVEX" in msgs[0]["content"]
    assert [m["role"] for m in msgs] == ["system", "user", "assistant", "user"]
    # the expert's samplers (temperature 0.7) win over the request defaults
    assert conn.samplers[0][0] == 0.7


def test_expert_chat_requires_corpus_for_statistical(sidecar):
    r = sidecar.post("/experts/lengua/chat", json={"expert": "lengua", "query": "qué es huevo"})
    assert r.status_code == 400
    assert "corpus" in r.json()["detail"]


@pytest.mark.skipif(not server._DASA_AVAILABLE, reason="DASA/SHARD not importable")
def test_expert_chat_uses_its_corpus(sidecar, monkeypatch, tmp_path):
    # a test expert pointing at the demo dataset
    cat = tmp_path / "experts.json"
    cat.write_text(json.dumps({"version": 1, "experts": [{
        "id": "demo-exp", "name": "Demo", "description": "d", "datasets": ["demo"],
        "default_mode": "statistical", "system_prompt": "Eres demo.", "top_k": 3,
        "samplers": {"temperature": 0.0, "max_tokens": 128}, "examples": ["x"],
    }]}), encoding="utf-8")
    monkeypatch.setattr(experts_mod, "CATALOG_FILE", cat)
    build_dataset(sidecar, "demo")

    target = demo_records()[0]
    r = sidecar.post("/experts/demo-exp/chat", json={"expert": "demo-exp", "query": record_to_text(target)})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["expert"] == "demo-exp"
    assert body["dataset"] == "demo"
    assert body["meta"]["corpus"] is True and body["meta"]["datasets"] == ["demo"]
    assert body["fragments"] and len(body["fragments"]) <= 3
    assert target["lemma"] in body["answer"]

    st = sidecar.get("/experts/demo-exp").json()["status"]
    assert st["ready"] is True and st["missing_datasets"] == []
