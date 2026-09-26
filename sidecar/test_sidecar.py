"""
End-to-end sidecar tests: build a real SHARD + IVF-PQ index from the DASA demo
dataset and exercise the HTTP API (datasets, chat, federated, compare, export,
OpenAI-compatible endpoint). Embeddings are a deterministic fake (see conftest).

Run:  python -m pytest sidecar -q   (from the KAMVEX repo root)
"""

from __future__ import annotations

import io
import json
import zipfile

import server
from conftest import build_dataset, demo_records, sse_stages
from jobs import record_to_text


def test_health_reports_capabilities(sidecar):
    h = sidecar.get("/health").json()
    assert h["status"] == "ok"
    assert h["version"] == server.VERSION
    assert "dasa" in h and "embeddings" in h


def test_build_list_and_statistical_chat(sidecar):
    build_dataset(sidecar, "demo")
    listed = sidecar.get("/datasets").json()
    demo = next(d for d in listed if d["name"] == "demo")
    assert demo["n_records"] == len(demo_records())
    assert demo["dim"] == 384
    assert demo["embedding_backend"] == "fake"
    assert (server.DATA_DIR / "demo" / "keys.json").exists()

    # query == record text -> fake vector matches the stored vector exactly
    target = demo_records()[0]
    q = record_to_text(target)
    resp = sidecar.post("/chat", json={"dataset": "demo", "query": q}).json()
    assert resp["mode"] == "statistical"
    assert resp["fragments"], "no fragments returned"
    top_text = resp["fragments"][0]["text"]
    assert str(target.get("definition", ""))[:20] in top_text or str(target.get("lemma", "")) in top_text
    assert resp["answer"]

    # grounded / free without an inference engine -> 503 con un mensaje que diga qué hacer,
    # nunca una respuesta silenciosa que parezca buena
    for mode in ("grounded", "free"):
        r = sidecar.post("/chat", json={"dataset": "demo", "query": q, "agent_b_mode": mode})
        assert r.status_code == 503, r.text
        assert "modelo" in r.json()["detail"].lower()
    assert sidecar.get("/inference/status").json()["connected"] is False


def test_chat_unknown_dataset_is_404(sidecar):
    r = sidecar.post("/chat", json={"dataset": "nope", "query": "hola"})
    assert r.status_code == 404


def test_build_from_text_and_export(sidecar):
    text = "\n".join(f"Párrafo número {i} sobre el tema {i}. " * 8 for i in range(6))
    r = sidecar.post("/datasets/build-text", json={"name": "texto", "text": text, "chunk_size": 300})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["n_chunks"] >= 2
    stages = sse_stages(sidecar.get(f"/datasets/build/{body['job_id']}/events").text)
    assert "done" in stages and "error" not in stages

    meta = next(d for d in sidecar.get("/datasets").json() if d["name"] == "texto")
    assert meta["n_records"] == body["n_chunks"]
    assert (server.DATA_DIR / "texto" / "records.json").exists()

    r = sidecar.get("/datasets/texto/export")
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("application/zip")
    names = zipfile.ZipFile(io.BytesIO(r.content)).namelist()
    assert "meta.json" in names and "fulltext.txt" in names


def test_build_rejects_bad_inputs(sidecar):
    r = sidecar.post("/datasets/build", json={"name": "x", "json_path": "C:/no/such/file.json"})
    assert r.status_code == 404
    r = sidecar.post("/datasets/build", json={"name": "x", "json_path": str(server._SIBLINGS / "DASA-main" / "README.md")})
    assert r.status_code == 400
    r = sidecar.post("/datasets/build-text", json={"name": "x", "text": "   "})
    assert r.status_code == 400


def test_delete_dataset(sidecar):
    build_dataset(sidecar, "borrar")
    assert (server.DATA_DIR / "borrar" / "meta.json").exists()
    r = sidecar.delete("/datasets/borrar")
    assert r.status_code == 200, r.text
    assert not (server.DATA_DIR / "borrar").exists()
    assert all(d["name"] != "borrar" for d in sidecar.get("/datasets").json())
    assert sidecar.delete("/datasets/borrar").status_code == 404


def test_federated_routes_to_best_dataset(sidecar):
    build_dataset(sidecar, "demo")
    q = record_to_text(demo_records()[1])
    resp = sidecar.post("/federated", json={"query": q}).json()
    assert resp["dataset"] == "demo"
    assert resp["score"] > 0.5
    assert resp["fragments"]


def test_compare_without_engine_marks_llm_side(sidecar):
    build_dataset(sidecar, "demo")
    q = record_to_text(demo_records()[0])
    resp = sidecar.post("/compare", json={"dataset": "demo", "query": q}).json()
    assert resp["a"]["mode"] == "statistical" and resp["a"]["answer"]
    assert resp["b"]["mode"] == "grounded" and resp["b"]["answer"] == "(sin motor de inferencia)"


def test_openai_compatible_endpoint(sidecar):
    build_dataset(sidecar, "demo")
    models = sidecar.get("/v1/models").json()
    assert any(m["id"] == "demo" for m in models["data"])

    q = record_to_text(demo_records()[0])
    r = sidecar.post("/v1/chat/completions", json={"model": "demo", "messages": [{"role": "user", "content": q}]})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["object"] == "chat.completion"
    assert body["choices"][0]["message"]["content"]

    r = sidecar.post("/v1/chat/completions",
                     json={"model": "kamvex", "stream": True, "messages": [{"role": "user", "content": q}]})
    assert r.status_code == 200
    assert "data: [DONE]" in r.text
    chunks = [json.loads(l[6:]) for l in r.text.splitlines() if l.startswith("data: ") and l != "data: [DONE]"]
    assert chunks[-1]["choices"][0]["finish_reason"] == "stop"

    r = sidecar.post("/v1/chat/completions", json={"model": "demo", "messages": [{"role": "system", "content": "x"}]})
    assert r.status_code == 400


def test_local_models_listing_and_delete(sidecar):
    (server.MODELS_DIR / "tiny.gguf").write_bytes(b"GGUF" + b"\0" * 64)
    (server.MODELS_DIR / "partial.gguf.part").write_bytes(b"\0" * 8)
    listed = sidecar.get("/models/local").json()
    assert [m["file"] for m in listed] == ["tiny.gguf"]
    assert listed[0]["path"].endswith("tiny.gguf")

    assert sidecar.delete("/models/local/tiny.gguf").status_code == 200
    assert sidecar.get("/models/local").json() == []
    assert sidecar.delete("/models/local/tiny.gguf").status_code == 404
