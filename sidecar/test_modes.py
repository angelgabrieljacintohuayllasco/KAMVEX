"""
Agent B modes through the sidecar:

    statistical — never touches the LLM
    grounded    — LLM only formats relevant fragments; if the corpus does not
                  cover the question it answers NOT_COVERED without calling the LLM
    free        — LLM answers from the corpus when relevant, freely otherwise
"""

from __future__ import annotations

import pytest

import server
from conftest import FakeConnector, build_dataset, demo_records
from jobs import record_to_text

pytestmark = pytest.mark.skipif(not server._DASA_AVAILABLE, reason="DASA/SHARD not importable")


def _pipe():
    from dasa.config import DASAConfig
    from dasa.pipeline import DASAPipeline
    return DASAPipeline(DASAConfig())


def _fragments(*scores):
    from dasa.agent_a.retrieval_agent import Fragment
    return [Fragment(text=f"dato número {i} del corpus", score=s, source_id=f"k{i}") for i, s in enumerate(scores)]


def _samplers(**kw):
    return server.SamplerFields(**kw)


def test_statistical_never_calls_llm(monkeypatch):
    conn = FakeConnector()
    monkeypatch.setattr(server, "_LLAMA_CONNECTOR", conn)
    answer = server._synthesize(_pipe(), "statistical", "¿qué dato hay?", _fragments(0.9, 0.8), _samplers())
    assert answer
    assert conn.calls == []


def test_grounded_without_relevant_fragments_does_not_invent(monkeypatch):
    conn = FakeConnector()
    monkeypatch.setattr(server, "_LLAMA_CONNECTOR", conn)
    pipe = _pipe()
    assert server._synthesize(pipe, "grounded", "hola", [], _samplers()) == server.NOT_COVERED
    assert server._synthesize(pipe, "grounded", "hola", _fragments(0.2, 0.39), _samplers()) == server.NOT_COVERED
    assert conn.calls == [], "grounded mode must not fall back to a free LLM answer"


def test_grounded_formats_relevant_fragments_under_strict_prompt(monkeypatch):
    conn = FakeConnector(reply="  El dato número 0 del corpus.  ")
    monkeypatch.setattr(server, "_LLAMA_CONNECTOR", conn)
    answer = server._synthesize(_pipe(), "grounded", "¿qué dato hay?", _fragments(0.95, 0.1), _samplers(max_tokens=64))
    assert answer == "El dato número 0 del corpus."
    assert len(conn.calls) == 1
    messages = conn.calls[0]
    assert isinstance(messages, list)
    joined = " ".join(m["content"] for m in messages)
    assert "CANDIDATOS" in joined          # prompt de Agente B
    assert "dato número 0" in joined and "dato número 1" not in joined  # low-score fragment excluded
    assert conn.samplers[0][4] == 64  # max_tokens forwarded
    assert conn.samplers[1].get("seed") == 42  # deterministic by default

    # a reply with words the corpus does not contain is replaced by the deterministic answer
    conn2 = FakeConnector(reply="Información inventada sobre volcanes y dinosaurios.")
    monkeypatch.setattr(server, "_LLAMA_CONNECTOR", conn2)
    answer, meta = server._synthesize_ex(_pipe(), "grounded", "¿qué dato hay?", _fragments(0.95), _samplers())
    assert meta["fallback"] is True and "dinosaurios" not in answer


def test_free_mode_answers_freely_without_corpus(monkeypatch):
    conn = FakeConnector(reply="charla libre")
    monkeypatch.setattr(server, "_LLAMA_CONNECTOR", conn)
    pipe = _pipe()
    original = pipe.agent_b._free_system_prompt
    answer = server._synthesize(pipe, "free", "hola", [], _samplers(), free_system_prompt="Eres un pirata.")
    assert answer == "charla libre"
    system = conn.calls[0][0]
    assert system["role"] == "system" and system["content"] == "Eres un pirata."
    assert pipe.agent_b._free_system_prompt == original, "client system prompt must not leak"


def test_invalid_mode_is_400():
    with pytest.raises(Exception) as exc:
        server._synthesize(_pipe(), "magic", "q", [], _samplers())
    assert getattr(exc.value, "status_code", None) == 400


def test_chat_api_grounded_uses_connector(sidecar, monkeypatch):
    build_dataset(sidecar, "demo")
    conn = FakeConnector(reply="anclado por el LLM")
    monkeypatch.setattr(server, "_LLAMA_CONNECTOR", conn)
    q = record_to_text(demo_records()[0])
    resp = sidecar.post("/chat", json={"dataset": "demo", "query": q, "agent_b_mode": "grounded", "guardrail": False}).json()
    assert resp["answer"] == "anclado por el LLM"
    assert resp["mode"] == "grounded"
    assert resp["meta"]["engine"] == "llm"
    assert len(conn.calls) == 1


def test_free_chat_keeps_history_and_system_prompt(sidecar, monkeypatch):
    conn = FakeConnector(reply="ok")
    monkeypatch.setattr(server, "_LLAMA_CONNECTOR", conn)
    r = sidecar.post("/chat/free", json={
        "query": "¿y ahora?",
        "system_prompt": "Responde en verso.",
        "history": [{"role": "user", "content": "hola"}, {"role": "assistant", "content": "buenas"},
                    {"role": "tool", "content": "ignorado"}],
    })
    assert r.status_code == 200, r.text
    assert r.json()["answer"] == "ok"
    messages = conn.calls[0]
    assert [m["role"] for m in messages] == ["system", "user", "assistant", "user"]
    assert messages[0]["content"] == "Responde en verso."
    assert messages[-1]["content"] == "¿y ahora?"


def test_free_chat_without_engine_is_400(sidecar):
    assert sidecar.post("/chat/free", json={"query": "hola"}).status_code == 400
