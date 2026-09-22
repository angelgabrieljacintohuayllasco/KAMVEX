"""
Shared fixtures for the sidecar test-suite.

Embeddings are replaced by a deterministic hash-based fake so every test is
offline and fast; datasets are built in a temporary directory.
"""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

import numpy as np
import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parent))

import server  # noqa: E402
from llama_connector import summarize_slots  # noqa: E402

DIM = 384
DEMO = (server._SIBLINGS / "DASA-main" / "data" / "demo_dataset.json") if server._SIBLINGS else None


def fake_vec(text: str, dim: int = DIM) -> np.ndarray:
    seed = int(hashlib.sha1(str(text).encode("utf-8")).hexdigest(), 16) % (2**32)
    v = np.random.default_rng(seed).standard_normal(dim).astype(np.float32)
    return v / np.linalg.norm(v)


class FakeEmbeddingEngine:
    """Same duck-typed contract as DASA's EmbeddingEngine, deterministic and offline."""

    def encode(self, text):
        return fake_vec(text)

    def encode_batch(self, texts):
        return np.stack([fake_vec(t) for t in texts])

    @staticmethod
    def cosine_similarity_batch(query_vec, corpus_vecs):
        return np.dot(corpus_vecs, query_vec)

    def describe(self):
        return {"backend": "fake", "model": "fake-384"}


class FakeConnector:
    """Records every prompt it receives and answers with a canned reply."""

    def __init__(self, reply: str = "respuesta simulada del LLM"):
        self.reply = reply
        self.calls: list = []
        self.samplers = None

    def set_samplers(self, *args, **kwargs):
        self.samplers = (args, kwargs)

    def __call__(self, messages):
        self.calls.append(messages)
        return self.reply

    def is_alive(self):
        return True

    def get_metrics(self):
        return summarize_slots([])


def sse_stages(text: str) -> list[str]:
    return [json.loads(line[6:])["stage"] for line in text.splitlines() if line.startswith("data: ")]


def build_dataset(client: TestClient, name: str = "demo", profile: str = "low-ram") -> None:
    assert DEMO is not None and DEMO.exists(), f"demo dataset missing: {DEMO}"
    r = client.post("/datasets/build", json={"name": name, "json_path": str(DEMO), "profile": profile})
    assert r.status_code == 200, r.text
    jid = r.json()["job_id"]
    stages = sse_stages(client.get(f"/datasets/build/{jid}/events").text)
    assert "error" not in stages, stages
    assert "done" in stages, stages


def demo_records() -> list[dict]:
    return json.loads(DEMO.read_text(encoding="utf-8"))


@pytest.fixture
def sidecar(tmp_path, monkeypatch):
    """TestClient over the sidecar with temp dirs, fake embeddings and no LLM."""
    data_dir = tmp_path / "datasets"
    models_dir = tmp_path / "models"
    data_dir.mkdir()
    models_dir.mkdir()
    monkeypatch.setattr(server, "DATA_DIR", data_dir)
    monkeypatch.setattr(server, "MODELS_DIR", models_dir)
    monkeypatch.setattr(server, "_embedding_engine", FakeEmbeddingEngine())
    monkeypatch.setattr(server, "_LLAMA_CONNECTOR", None)
    server._PIPELINES.clear()
    with TestClient(server.app) as client:
        yield client
    for name in list(server._PIPELINES):
        server._close_pipeline(name)
