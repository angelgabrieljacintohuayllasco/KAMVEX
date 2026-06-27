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
        self._model = model
        self._timeout = timeout

    def __call__(self, messages) -> str:
        if isinstance(messages, str):
            messages = [{"role": "user", "content": messages}]
        body = json.dumps({
            "model": self._model,
            "messages": messages,
            "stream": False,
            "temperature": 0.1,
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
            req = urllib.request.Request(
                f"http://{self._host}:{self._port}/health"
            )
            urllib.request.urlopen(req, timeout=3)
            return True
        except Exception:
            return False
