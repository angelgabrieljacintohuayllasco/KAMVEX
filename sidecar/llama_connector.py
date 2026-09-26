"""
LlamaCppConnector — callable that sends prompts to a llama-server instance.

Follows the duck-typed LLM connector protocol of DASA's Agent B:
a callable `(messages_or_str) -> str`. Inject via:

    pipeline.agent_b._llm_callable = LlamaCppConnector(host, port)
"""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.request

DEFAULT_MAX_TOKENS = 512
# llama-server contesta 503 mientras carga el .gguf en memoria. Cambiar de modelo y
# preguntar enseguida es lo normal, así que se espera en vez de fallar: el usuario veía
# "Failed to fetch" por pulsar Enter dos segundos antes de tiempo.
LOADING_RETRY_SECONDS = 90.0
LOADING_POLL_SECONDS = 1.0
# Small Instruct models sometimes keep generating past their own turn; these
# ChatML markers stop the runaway (harmless for models that never emit them).
DEFAULT_STOP = ["<|im_end|>", "<|im_start|>"]


class LlamaCppConnector:
    """Talk to llama-server's OpenAI-compatible /v1/chat/completions endpoint."""

    def __init__(self, host: str = "127.0.0.1", port: int = 8766,
                 model: str = "local", timeout: float = 300.0,
                 max_tokens: int = DEFAULT_MAX_TOKENS):
        self._host = host
        self._port = port
        self._base = f"http://{host}:{port}/v1/chat/completions"
        self._health_url = f"http://{host}:{port}/health"
        self._slots_url = f"http://{host}:{port}/slots"
        self._model = model
        self._timeout = timeout
        self._temperature = 0.1
        self._top_p = 0.95
        self._top_k = 40
        self._repeat_penalty = 1.0
        self._max_tokens = max_tokens
        self._seed: int | None = None

    @property
    def endpoint(self) -> str:
        return f"http://{self._host}:{self._port}"

    def set_samplers(self, temperature: float, top_p: float, top_k: int,
                     repeat_penalty: float, max_tokens: int | None = None,
                     seed: int | None = None):
        self._temperature = float(temperature)
        self._top_p = float(top_p)
        self._top_k = int(top_k)
        self._repeat_penalty = float(repeat_penalty)
        if max_tokens is not None and max_tokens > 0:
            self._max_tokens = int(max_tokens)
        self._seed = seed

    def set_deterministic(self, seed: int = 42, max_tokens: int | None = None):
        """Greedy decoding with a fixed seed: same prompt → same answer.
        A mild repeat penalty keeps small models from looping; still deterministic."""
        self.set_samplers(0.0, 1.0, 1, 1.1, max_tokens, seed=seed)

    def request_body(self, messages) -> dict:
        """Build the request payload (exposed for tests)."""
        if isinstance(messages, str):
            messages = [{"role": "user", "content": messages}]
        body = {
            "model": self._model,
            "messages": messages,
            "stream": False,
            "temperature": self._temperature,
            "top_p": self._top_p,
            "top_k": self._top_k,
            "repeat_penalty": self._repeat_penalty,
            "max_tokens": self._max_tokens,
            "stop": DEFAULT_STOP,
        }
        if self._seed is not None:
            body["seed"] = int(self._seed)
        return body

    def __call__(self, messages) -> str:
        body = json.dumps(self.request_body(messages)).encode("utf-8")
        deadline = time.monotonic() + LOADING_RETRY_SECONDS
        while True:
            req = urllib.request.Request(
                self._base, data=body,
                headers={"Content-Type": "application/json"},
            )
            try:
                with urllib.request.urlopen(req, timeout=self._timeout) as resp:
                    data = json.loads(resp.read())
                    return (data["choices"][0]["message"]["content"] or "").strip()
            except urllib.error.HTTPError as e:
                detail = ""
                try:
                    detail = e.read().decode("utf-8", "replace")[:300]
                except Exception:  # noqa: BLE001
                    pass
                if e.code == 503 and time.monotonic() < deadline:
                    time.sleep(LOADING_POLL_SECONDS)   # sigue cargando el modelo
                    continue
                if e.code == 503:
                    raise RuntimeError(
                        "el modelo sigue cargando; inténtalo de nuevo en unos segundos") from e
                raise RuntimeError(f"llama-server respondió HTTP {e.code}: {detail}") from e
            except urllib.error.URLError as e:
                raise RuntimeError(f"llama-server no disponible: {e}") from e

    def is_alive(self) -> bool:
        """Check if the server is responding."""
        try:
            req = urllib.request.Request(self._health_url)
            urllib.request.urlopen(req, timeout=3)
            return True
        except Exception:  # noqa: BLE001
            return False

    def get_metrics(self) -> dict:
        """Fetch metrics from llama-server's /slots endpoint.

        Extracts: active_slots, total_decoded, tokens_per_second (predicted),
        ttft_ms (prompt processing time), context_used, context_total, context_pct.
        """
        try:
            req = urllib.request.Request(self._slots_url)
            with urllib.request.urlopen(req, timeout=3) as resp:
                slots = json.loads(resp.read())
        except Exception:  # noqa: BLE001
            return summarize_slots([])
        if not isinstance(slots, list):
            return summarize_slots([])
        return summarize_slots(slots)


def _as_dict(value) -> dict:
    """Un campo de /slots que puede venir como dict o como lista de dicts.

    Las compilaciones recientes de llama.cpp devuelven `next_token` (y a veces `timings`)
    envuelto en una lista. Esperar solo el dict tiraba /inference/metrics con
    "'list' object has no attribute 'get'", y la app mostraba "Motor inactivo" con el
    modelo cargado y respondiendo.
    """
    if isinstance(value, dict):
        return value
    if isinstance(value, list):
        for item in value:
            if isinstance(item, dict):
                return item
    return {}


def summarize_slots(slots: list[dict]) -> dict:
    """Reduce llama-server's /slots payload to the dashboard numbers."""
    total_decoded = 0
    active = 0
    tokens_per_second = 0.0
    ttft_ms = 0.0
    context_used = 0
    context_total = 0

    for slot in slots:
        if not isinstance(slot, dict):
            continue
        if slot.get("is_processing"):
            active += 1

        nt = _as_dict(slot.get("next_token"))
        total_decoded += int(nt.get("n_decoded", 0) or 0)

        timings = _as_dict(slot.get("timings"))
        tokens_per_second = max(tokens_per_second, float(timings.get("predicted_per_second", 0.0) or 0.0))
        ttft_ms = max(ttft_ms, float(timings.get("prompt_ms", 0.0) or 0.0))

        context_total = max(context_total, int(slot.get("n_ctx", 0) or 0))
        context_used = max(context_used, int(slot.get("n_tokens", 0) or 0))

    context_pct = round(context_used / context_total * 100, 1) if context_total > 0 else 0.0
    return {
        "active_slots": active,
        "total_decoded": total_decoded,
        "tokens_per_second": round(tokens_per_second, 1),
        "ttft_ms": round(ttft_ms, 1),
        "context_used": context_used,
        "context_total": context_total,
        "context_pct": context_pct,
        "slots": slots,
    }
