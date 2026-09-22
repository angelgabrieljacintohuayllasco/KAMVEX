"""
LlamaEmbeddingEngine — unit tests (no server) and an integration test that
spawns the real llama-server with the MiniLM GGUF when both are present.
"""

from __future__ import annotations

import sys

import numpy as np
import pytest

import paths
import server
from conftest import build_dataset, demo_records, sse_stages
from embedding_gguf import MAX_CHARS, LlamaEmbeddingEngine, DEFAULT_FILE
from jobs import record_to_text

REAL_BIN = paths.llama_server_binary()
REAL_MODEL = paths.models_dir() / "embeddings" / DEFAULT_FILE
HAVE_REAL = REAL_BIN is not None and REAL_MODEL.is_file()


def _stub_engine(monkeypatch, dim=3):
    eng = LlamaEmbeddingEngine("nonexistent-bin", "nonexistent-model")
    monkeypatch.setattr(eng, "start", lambda: None)
    monkeypatch.setattr(eng, "_post_embeddings", lambda texts: [[1.0, 2.0, 2.0][:dim] for _ in texts])
    return eng


def test_prepare_truncates_and_never_sends_empty():
    assert LlamaEmbeddingEngine._prepare("") == " "
    assert LlamaEmbeddingEngine._prepare("  hola  ") == "hola"
    assert len(LlamaEmbeddingEngine._prepare("x" * (MAX_CHARS + 500))) == MAX_CHARS


def test_encode_batch_normalizes_rows(monkeypatch):
    eng = _stub_engine(monkeypatch)
    arr = eng.encode_batch(["a", "b"])
    assert arr.shape == (2, 3) and arr.dtype == np.float32
    assert np.allclose(np.linalg.norm(arr, axis=1), 1.0)
    assert eng.dim == 3
    assert eng.encode("a").shape == (3,)


def test_missing_binary_raises_clear_error():
    eng = LlamaEmbeddingEngine("nonexistent-bin", "nonexistent-model")
    with pytest.raises(RuntimeError, match="llama-server no encontrado"):
        eng.start()


def test_command_line_shape():
    eng = LlamaEmbeddingEngine("bin", "model.gguf", ctx=256, threads=2)
    cmd = eng._command(4321)
    assert "--embedding" in cmd and "--pooling" in cmd and "mean" in cmd
    assert cmd[cmd.index("--port") + 1] == "4321"
    assert cmd[cmd.index("-t") + 1] == "2"
    assert "--no-webui" in cmd
    # the physical batch must hold a whole request, otherwise llama-server answers 500
    from embedding_gguf import BATCH_TOKEN_BUDGET, PHYSICAL_BATCH
    assert int(cmd[cmd.index("-b") + 1]) == PHYSICAL_BATCH >= BATCH_TOKEN_BUDGET
    assert int(cmd[cmd.index("-ub") + 1]) == PHYSICAL_BATCH


def test_batches_respect_token_budget(monkeypatch):
    from embedding_gguf import BATCH_SIZE, BATCH_TOKEN_BUDGET, CHARS_PER_TOKEN
    eng = LlamaEmbeddingEngine("bin", "model.gguf")
    long_texts = ["x" * 1200] * 40
    batches = list(eng._batches(long_texts))
    assert all(sum(len(t) for t in b) / CHARS_PER_TOKEN <= BATCH_TOKEN_BUDGET or len(b) == 1 for b in batches)
    assert sum(len(b) for b in batches) == 40
    short = list(eng._batches(["hola"] * 100))
    assert all(len(b) <= BATCH_SIZE for b in short)


def test_embed_chunk_splits_on_http_error(monkeypatch):
    """A 500 ("batch too large") must be recovered by splitting, not by failing."""
    import urllib.error
    eng = LlamaEmbeddingEngine("bin", "model.gguf")
    seen: list[int] = []

    def fake_post(texts):
        seen.append(len(texts))
        if len(texts) > 2:
            raise urllib.error.HTTPError("u", 500, "too large", None, None)
        return [[1.0, 0.0, 0.0] for _ in texts]

    monkeypatch.setattr(eng, "_post_embeddings", fake_post)
    out = eng._embed_chunk(["a"] * 8)
    assert len(out) == 8
    assert seen[0] == 8 and max(seen[1:]) <= 4


@pytest.mark.skipif(sys.platform != "win32", reason="Windows job objects")
def test_job_object_kills_child_when_handle_closes():
    """The embedding server must die with the sidecar even on TerminateProcess."""
    import ctypes
    import subprocess
    import time
    from embedding_gguf import _assign_to_job, _kill_on_close_job

    job = _kill_on_close_job()
    assert job, "CreateJobObject failed"
    child = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(60)"],
                             creationflags=0x08000000)
    try:
        assert _assign_to_job(job, child) is True
        assert child.poll() is None
        ctypes.windll.kernel32.CloseHandle(job)   # what the OS does when the sidecar dies
        deadline = time.time() + 5
        while child.poll() is None and time.time() < deadline:
            time.sleep(0.1)
        assert child.poll() is not None, "child survived the job close"
    finally:
        if child.poll() is None:
            child.kill()


@pytest.mark.skipif(not HAVE_REAL, reason="llama-server binary or MiniLM GGUF not present")
def test_real_llama_server_embeddings_are_semantic():
    eng = LlamaEmbeddingEngine(REAL_BIN, REAL_MODEL)
    try:
        arr = eng.encode_batch([
            "El perro corre por el parque",
            "Un can corriendo en el jardín",
            "Declaración anual de impuestos ante SUNAT",
        ])
        assert arr.shape == (3, 384)
        assert np.allclose(np.linalg.norm(arr, axis=1), 1.0, atol=1e-3)
        sim_related = float(arr[0] @ arr[1])
        sim_unrelated = float(arr[0] @ arr[2])
        # MiniLM is English-centric: Spanish pairs separate less, but ordering must hold.
        assert sim_related > sim_unrelated + 0.05, (sim_related, sim_unrelated)
        assert eng.running and eng.port
        assert eng.describe()["backend"] == "llama-gguf"
    finally:
        eng.stop()
    assert not eng.running


@pytest.mark.skipif(not HAVE_REAL or not server._DASA_AVAILABLE, reason="needs real engine + DASA")
def test_end_to_end_build_and_chat_with_gguf_embeddings(sidecar, monkeypatch):
    eng = LlamaEmbeddingEngine(REAL_BIN, REAL_MODEL)
    monkeypatch.setattr(server, "_embedding_engine", eng)
    try:
        build_dataset(sidecar, "demo-gguf")
        meta = next(d for d in sidecar.get("/datasets").json() if d["name"] == "demo-gguf")
        assert meta["embedding_backend"] == "llama-gguf" and meta["dim"] == 384

        target = demo_records()[0]
        q = f"¿Qué es {target['lemma']}?"
        resp = sidecar.post("/chat", json={"dataset": "demo-gguf", "query": q}).json()
        assert resp["fragments"], resp
        assert target["lemma"].lower() in resp["fragments"][0]["text"].lower()
        assert resp["answer"]
        assert sidecar.get("/embeddings/status").json()["backend"] == "llama-gguf"
    finally:
        for name in list(server._PIPELINES):
            server._close_pipeline(name)
        eng.stop()
