"""
Sidecar test: build a real SHARD+IVF index from the DASA demo dataset and chat
over it, end to end, through the FastAPI app. Embeddings are monkeypatched to a
deterministic fake so the test is offline and fast (no MiniLM download).

Run:  python -m pytest test_sidecar.py   (from DASA-UI/sidecar/)
      or:  python test_sidecar.py
"""

import hashlib
import json
import tempfile
from pathlib import Path

import numpy as np
from fastapi.testclient import TestClient

import server
from jobs import record_to_text
from dasa.agent_a.embeddings import EmbeddingEngine

DIM = 384
DEMO = server._PARENT_OF_REPOS / "DASA-main" / "data" / "demo_dataset.json"


def _vec(text, dim=DIM):
    seed = int(hashlib.sha1(text.encode("utf-8")).hexdigest(), 16) % (2**32)
    v = np.random.default_rng(seed).standard_normal(dim).astype(np.float32)
    return v / np.linalg.norm(v)


def _install_fake_embeddings():
    EmbeddingEngine.encode = lambda self, text: _vec(text)
    EmbeddingEngine.encode_batch = lambda self, texts: np.stack([_vec(t) for t in texts])


def _sse_done(text: str) -> bool:
    stages = [json.loads(l[6:])["stage"] for l in text.splitlines() if l.startswith("data: ")]
    assert "error" not in stages, f"build emitted error: {text}"
    return "done" in stages


def test_build_and_chat():
    _install_fake_embeddings()
    assert DEMO.exists(), f"demo dataset missing: {DEMO}"
    records = json.loads(DEMO.read_text(encoding="utf-8"))

    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as td:
        server.DATA_DIR = Path(td)
        client = TestClient(server.app)

        assert client.get("/health").json()["status"] == "ok"

        r = client.post("/datasets/build",
                        json={"name": "demo", "json_path": str(DEMO), "profile": "low-ram"})
        assert r.status_code == 200, r.text
        jid = r.json()["job_id"]
        assert _sse_done(client.get(f"/datasets/build/{jid}/events").text)

        assert any(d["name"] == "demo" for d in client.get("/datasets").json())

        # query == record text -> fake vector matches the stored vector exactly
        target = records[0]
        q = record_to_text(target)
        resp = client.post("/chat", json={"dataset": "demo", "query": q}).json()
        assert resp["fragments"], "no fragments returned"
        top_text = resp["fragments"][0]["text"]
        # the top fragment should be the record we queried
        assert str(target.get("definition", "")) [:20] in top_text or \
               str(target.get("lemma", "")) in top_text, f"unexpected top: {top_text!r}"
        print(f"OK — answer={resp['answer'][:60]!r}  frags={len(resp['fragments'])}")

        # Agent B mode: statistical should work without inference engine
        resp2 = client.post("/chat", json={"dataset": "demo", "query": q, "agent_b_mode": "statistical"}).json()
        assert resp2["mode"] == "statistical"
        assert "answer" in resp2

        # Agent B mode: grounded without inference engine → 400
        r400 = client.post("/chat", json={"dataset": "demo", "query": q, "agent_b_mode": "grounded"})
        assert r400.status_code == 400

        # Inference status: disconnected by default
        assert client.get("/inference/status").json()["connected"] is False


def test_llama_connector_protocol():
    """LlamaCppConnector follows the (messages) -> str callable protocol."""
    from llama_connector import LlamaCppConnector
    c = LlamaCppConnector("127.0.0.1", 9999)
    assert callable(c)
    assert c.is_alive() is False  # no server on port 9999


if __name__ == "__main__":
    test_build_and_chat()
    test_llama_connector_protocol()
    print("OK")
