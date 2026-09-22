"""
Grounding helpers + their effect on the Agent B modes (exact answers, guardrail, determinism).
"""

from __future__ import annotations

import pytest

import server
from conftest import FakeConnector, build_dataset, demo_records
from grounding import (content_terms, coverage, exact_definition_answer, extract_term,
                       focus_text, grounded_messages, trim_fragments)


class Frag:
    def __init__(self, text, score=0.9, source_id=None):
        self.text, self.score, self.source_id = text, score, source_id


def test_extract_term():
    assert extract_term("¿Qué es huevo?") == "huevo"
    assert extract_term("que significa efímero") == "efímero"
    assert extract_term("Define serendipia.") == "serendipia"
    assert extract_term("What is an egg?") == "egg"
    assert extract_term("¿Qué dice el artículo 2?") == "artículo 2"


def test_content_terms_and_coverage():
    frags = [Frag("huevo: Cuerpo redondeado producido por las aves, que contiene el embrión de la cría.", source_id="huevo")]
    assert "huevo" in content_terms("el huevo y los huevos") or "huevo"[:5] in content_terms("el huevo")
    cov, missing = coverage("El huevo es un cuerpo redondeado producido por las aves.", frags)
    assert cov == 1.0 and missing == []
    cov, missing = coverage("El huevo contiene mucho orégano y tomillo aromático.", frags)
    assert cov < 0.85
    assert any(m.startswith("orega") or m.startswith("oreg") for m in missing)
    assert coverage("", frags) == (1.0, [])


def test_exact_definition_answer():
    frags = [
        Frag("huevo frito: Preparación culinaria que consiste en freír el huevo.", 0.8, "huevo frito"),
        Frag("huevo: Cuerpo redondeado producido por las aves.", 0.79, "huevo"),
    ]
    assert exact_definition_answer("¿Qué es huevo?", frags) == "huevo: Cuerpo redondeado producido por las aves."
    assert exact_definition_answer("¿Qué es huevo frito?", frags).startswith("huevo frito:")
    assert exact_definition_answer("¿Qué es tortilla?", frags) is None
    # disambiguated keys ("huevo#1") still match
    assert exact_definition_answer("qué es huevo", [Frag("huevo: x", 0.5, "huevo#1")]) == "huevo: x"


def test_focus_text_keeps_the_answering_sentence():
    text = (
        "Departamento de Amazonas (Perú): Amazonas es uno de los veinticuatro departamentos "
        "que conforman la República del Perú. Su capital es Chachapoyas y su ciudad más poblada "
        "es Bagua Grande. " + "Abarca territorio de selva con ríos y montañas. " * 40
    )
    focused = focus_text("¿Cuál es la capital del departamento de Amazonas?", text, max_chars=400)
    assert len(focused) <= 400
    assert "Chachapoyas" in focused
    assert focused.startswith("Departamento de Amazonas"), "the opening sentence gives the context"
    # short texts pass through untouched
    assert focus_text("x", "corto.", max_chars=400) == "corto."


def test_trim_fragments_focuses_each_fragment():
    long_text = "Tema: introducción. " + "relleno sin relación. " * 100 + "El dato clave es 42."
    frags = [Frag(long_text), Frag("otro"), Frag("tercero"), Frag("cuarto")]
    out = trim_fragments(frags, "¿cuál es el dato clave?")
    assert len(out) == 3, "only the top fragments are sent"
    assert "dato clave es 42" in out[0].text
    assert len(out[0].text) <= 900


def test_grounded_messages_language_and_example():
    es = grounded_messages("¿Qué es huevo?", [Frag("huevo: cuerpo")])
    assert es[0]["role"] == "system" and "español" in es[0]["content"]
    assert "CONTEXTO" in es[-1]["content"] and es[-1]["role"] == "user"
    # a worked example keeps small models from answering "no cubre" when the answer is there
    assert [m["role"] for m in es] == ["system", "user", "assistant", "user", "assistant", "user"]
    assert "Tacna" in es[1]["content"]
    en = grounded_messages("What is an egg?", [Frag("egg: body")])
    assert "CONTEXT:" in en[-1]["content"] and "QUESTION" in en[-1]["content"]
    assert len(en) == 6


@pytest.mark.skipif(not server._DASA_AVAILABLE, reason="DASA/SHARD not importable")
def test_key_hits_are_ranked_so_only_the_best_reaches_the_context(sidecar, monkeypatch):
    """Ambiguous names must not put contradictory records in the grounded context."""
    from keyindex import KEY_HIT_SCORE
    build_dataset(sidecar, "demo")
    pipe = server._load_pipeline("demo")

    class FakeIndex:
        def match(self, q, limit=3):
            return [r["lemma"] for r in demo_records()[:3]]

    monkeypatch.setitem(server._KEY_INDEXES, "demo", FakeIndex())
    hits = server._key_hits(pipe, "cualquier cosa")
    assert len(hits) == 3
    assert [round(h.score, 2) for h in hits] == [1.0, 0.98, 0.96]
    top = [h for h in hits if h.score >= KEY_HIT_SCORE]
    assert len(top) == 1, "only the best key hit is authoritative"


def test_search_query_normalization():
    assert server.search_query("¿Qué es huevo?") == "Qué es huevo"
    assert server.search_query("  ¡hola!  ") == "hola"
    assert server.search_query("huevo: cuerpo redondeado.") == "huevo: cuerpo redondeado."
    assert server.search_query("???") == "???"


@pytest.mark.skipif(not server._DASA_AVAILABLE, reason="DASA/SHARD not importable")
def test_statistical_mode_returns_exact_definition(sidecar):
    build_dataset(sidecar, "demo")
    target = demo_records()[0]
    # Fake embeddings only match the record's own text; the exact-answer logic then keys on "huevo".
    q = f"{target['lemma']}: {target['definition']}"
    resp = sidecar.post("/chat", json={"dataset": "demo", "query": q}).json()
    assert resp["answer"] == f"{target['lemma']}: {target['definition']}"
    assert resp["meta"]["engine"] == "exact"
    assert resp["meta"]["search_ms"] >= 0


@pytest.mark.skipif(not server._DASA_AVAILABLE, reason="DASA/SHARD not importable")
def test_grounded_guardrail_falls_back_on_hallucination(sidecar, monkeypatch):
    build_dataset(sidecar, "demo")
    target = demo_records()[0]
    q = f"{target['lemma']}: {target['definition']}"

    # 1) LLM answer fully covered by the corpus → accepted, deterministic settings used
    good = FakeConnector(reply=f"{target['lemma']}: {target['definition']}")
    monkeypatch.setattr(server, "_LLAMA_CONNECTOR", good)
    resp = sidecar.post("/chat", json={"dataset": "demo", "query": q, "agent_b_mode": "grounded"}).json()
    assert resp["meta"]["engine"] == "llm" and resp["meta"].get("fallback") is None
    assert resp["meta"]["coverage"] >= 0.85
    assert good.samplers[0][0] == 0.0 and good.samplers[1].get("seed") == 42, "greedy + fixed seed"

    # 2) LLM invents ingredients → coverage low → deterministic fallback, LLM text kept in meta
    bad = FakeConnector(reply="Se prepara con orégano, tomillo, cúrcuma, azafrán y wasabi importado de Japón.")
    monkeypatch.setattr(server, "_LLAMA_CONNECTOR", bad)
    resp = sidecar.post("/chat", json={"dataset": "demo", "query": q, "agent_b_mode": "grounded"}).json()
    assert resp["meta"]["fallback"] is True
    assert resp["meta"]["coverage"] < 0.85
    assert "orégano" not in resp["answer"] and "wasabi" not in resp["answer"]
    assert resp["answer"] == f"{target['lemma']}: {target['definition']}"

    # 3) guardrail can be switched off by the client
    resp = sidecar.post("/chat", json={"dataset": "demo", "query": q, "agent_b_mode": "grounded", "guardrail": False}).json()
    assert resp["answer"].startswith("Se prepara con orégano")
    assert "coverage" not in resp["meta"]
