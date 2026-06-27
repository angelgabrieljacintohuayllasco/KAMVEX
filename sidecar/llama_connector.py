"""
LlamaCppConnector — callable that sends prompts to a llama-server instance.

Follows the duck-typed LLM connector protocol of DASA's Agent B:
a callable `(messages_or_str) -> str`. Inject via:

    pipeline.agent_b._llm_callable = LlamaCppConnector(host, port)
"""

import json
import urllib.request
import urllib.error


class LlamaCppConnector:
    """Talk to llama-server's OpenAI-compatible /v1/chat/completions endpoint."""

    def __init__(self, host: str = "127.0.0.1", port: int = 8766,
                 model: str = "local", timeout: float = 120.0):
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

    def set_samplers(self, temperature: float, top_p: float, top_k: int, repeat_penalty: float):
        self._temperature = temperature
        self._top_p = top_p
        self._top_k = top_k
        self._repeat_penalty = repeat_penalty

    def __call__(self, messages) -> str:
        if isinstance(messages, str):
            messages = [{"role": "user", "content": messages}]
        body = json.dumps({
            "model": self._model,
            "messages": messages,
            "stream": False,
            "temperature": self._temperature,
            "top_p": self._top_p,
            "top_k": self._top_k,
            "repeat_penalty": self._repeat_penalty,
        }).encode("utf-8")
        req = urllib.request.Request(
            self._base, data=body,
            headers={"Content-Type": "application/json"},
        )
        try:
            with urllib.request.urlopen(req, timeout=self._timeout) as resp:
                data = json.loads(resp.read())
                return data["choices"][0]["message"]["content"]
        except urllib.error.URLError as e:
            raise RuntimeError(f"llama-server no disponible: {e}") from e

    def is_alive(self) -> bool:
        """Check if the server is responding."""
        try:
            req = urllib.request.Request(self._health_url)
            urllib.request.urlopen(req, timeout=3)
            return True
        except Exception:
            return False

    def get_metrics(self) -> dict:
        """Fetch metrics from llama-server's /slots endpoint."""
        try:
            req = urllib.request.Request(self._slots_url)
            with urllib.request.urlopen(req, timeout=3) as resp:
                slots = json.loads(resp.read())
                # Aggregate metrics from active slots
                total_decoded = 0
                active = 0
                for slot in slots:
                    if slot.get("is_processing"):
                        active += 1
                    nt = slot.get("next_token", {})
                    total_decoded += nt.get("n_decoded", 0)
                return {"active_slots": active, "total_decoded": total_decoded, "slots": slots}
        except Exception:
            return {"active_slots": 0, "total_decoded": 0, "slots": []}
