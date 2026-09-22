"""
LlamaCppConnector: request shape, sampler handling and /slots summarisation.
"""

from __future__ import annotations

from llama_connector import DEFAULT_STOP, LlamaCppConnector, summarize_slots


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
