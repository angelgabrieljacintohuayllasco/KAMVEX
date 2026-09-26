"""
LlamaCppConnector: request shape, sampler handling and /slots summarisation.
"""

from __future__ import annotations

import json
import urllib.error

import pytest

from llama_connector import DEFAULT_STOP, LlamaCppConnector, summarize_slots


class _FakeResponse:
    """Respuesta mínima de urlopen: lo que devuelve llama-server ya cargado."""

    def __init__(self, payload):
        self._payload = payload

    def read(self):
        return json.dumps(self._payload).encode("utf-8")

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def test_connector_is_callable_and_offline():
    c = LlamaCppConnector("127.0.0.1", 9999)
    assert callable(c)
    assert c.is_alive() is False  # nothing listens on 9999
    assert c.endpoint == "http://127.0.0.1:9999"


def test_request_body_caps_generation():
    c = LlamaCppConnector("127.0.0.1", 9999)
    body = c.request_body("hola")
    assert body["messages"] == [{"role": "user", "content": "hola"}]
    assert body["max_tokens"] == 512
    assert body["stop"] == DEFAULT_STOP
    assert body["stream"] is False

    c.set_samplers(0.5, 0.9, 20, 1.1, max_tokens=64)
    body = c.request_body([{"role": "system", "content": "s"}, {"role": "user", "content": "u"}])
    assert body["temperature"] == 0.5 and body["top_p"] == 0.9
    assert body["top_k"] == 20 and body["repeat_penalty"] == 1.1
    assert body["max_tokens"] == 64
    assert body["messages"][0]["role"] == "system"


def test_summarize_slots():
    slots = [
        {"id": 0, "is_processing": True, "n_ctx": 4096, "n_tokens": 1024,
         "next_token": {"n_decoded": 50}, "timings": {"predicted_per_second": 12.5, "prompt_ms": 300.0}},
        {"id": 1, "is_processing": False, "n_ctx": 4096, "n_tokens": 10,
         "next_token": {"n_decoded": 5}, "timings": {}},
    ]
    m = summarize_slots(slots)
    assert m["active_slots"] == 1
    assert m["total_decoded"] == 55
    assert m["tokens_per_second"] == 12.5
    assert m["ttft_ms"] == 300.0
    assert m["context_used"] == 1024 and m["context_total"] == 4096
    assert m["context_pct"] == 25.0

    empty = summarize_slots([])
    assert empty["active_slots"] == 0 and empty["context_pct"] == 0.0


def test_metrics_without_server_is_empty():
    m = LlamaCppConnector("127.0.0.1", 9999).get_metrics()
    assert m["active_slots"] == 0 and m["slots"] == []


# ── Cargar el modelo tarda: 503 no es un fallo, es "espera" ─────────────────

def test_espera_mientras_el_modelo_carga(monkeypatch):
    """Cambiar de modelo y preguntar enseguida daba "Failed to fetch" en la app."""
    import llama_connector as lc

    calls = {"n": 0}

    def fake_urlopen(req, timeout=None):
        calls["n"] += 1
        if calls["n"] < 3:
            raise urllib.error.HTTPError(req.full_url, 503, "Loading model", {}, None)
        return _FakeResponse({"choices": [{"message": {"content": "listo"}}]})

    monkeypatch.setattr(lc.urllib.request, "urlopen", fake_urlopen)
    monkeypatch.setattr(lc.time, "sleep", lambda _s: None)
    assert lc.LlamaCppConnector()("hola") == "listo"
    assert calls["n"] == 3


def test_si_tarda_demasiado_lo_dice_en_claro(monkeypatch):
    import llama_connector as lc

    def always_503(req, timeout=None):
        raise urllib.error.HTTPError(req.full_url, 503, "Loading model", {}, None)

    monkeypatch.setattr(lc.urllib.request, "urlopen", always_503)
    monkeypatch.setattr(lc.time, "sleep", lambda _s: None)
    monkeypatch.setattr(lc, "LOADING_RETRY_SECONDS", 0.0)
    with pytest.raises(RuntimeError, match="sigue cargando"):
        lc.LlamaCppConnector()("hola")


def test_otros_errores_http_no_se_reintentan(monkeypatch):
    import llama_connector as lc

    calls = {"n": 0}

    def boom(req, timeout=None):
        calls["n"] += 1
        raise urllib.error.HTTPError(req.full_url, 400, "Bad Request", {}, None)

    monkeypatch.setattr(lc.urllib.request, "urlopen", boom)
    with pytest.raises(RuntimeError, match="HTTP 400"):
        lc.LlamaCppConnector()("hola")
    assert calls["n"] == 1


# ── /slots cambia de forma entre compilaciones de llama.cpp ────────────────

# Carga real de la compilación que trae KAMVEX: `next_token` viene envuelto en una lista
# y `timings` puede ser null. Con el código anterior esto tiraba /inference/metrics.
SLOTS_NEXT_TOKEN_EN_LISTA = [
    {"id": 0, "n_ctx": 2048, "is_processing": False},
    {"id": 3, "n_ctx": 2048, "is_processing": True, "n_tokens": 312, "timings": None,
     "next_token": [{"has_next_token": False, "n_remain": 491, "n_decoded": 21}]},
]


def test_metricas_con_next_token_en_lista():
    m = summarize_slots(SLOTS_NEXT_TOKEN_EN_LISTA)
    assert m["active_slots"] == 1
    assert m["total_decoded"] == 21
    assert m["context_total"] == 2048 and m["context_used"] == 312
    assert m["tokens_per_second"] == 0 and m["ttft_ms"] == 0


def test_metricas_con_la_forma_clasica():
    m = summarize_slots([
        {"id": 0, "n_ctx": 4096, "is_processing": True, "n_tokens": 100,
         "next_token": {"n_decoded": 7},
         "timings": {"predicted_per_second": 12.5, "prompt_ms": 340.0}},
    ])
    assert m["total_decoded"] == 7
    assert m["tokens_per_second"] == 12.5 and m["ttft_ms"] == 340.0
    assert m["context_pct"] == round(100 / 4096 * 100, 1)


def test_metricas_con_basura_no_revientan():
    assert summarize_slots([])["active_slots"] == 0
    assert summarize_slots([[], None, "x"])["active_slots"] == 0
