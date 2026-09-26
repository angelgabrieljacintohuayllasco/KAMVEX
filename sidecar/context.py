"""
Cuánto cabe en el modelo, y cómo recortar cuando no cabe.

llama-server no perdona: si el prompt supera `n_ctx` devuelve un 400 y la respuesta no
llega. El usuario no ve «el prompt es largo», ve la aplicación rota. Así que se mide antes
de enviar y se recorta por orden de lo que menos duele perder:

    1. los turnos viejos de la conversación — dan contexto, no responden la pregunta
    2. las fuentes de más abajo — la primera es la que el Agente A puso delante
    3. el texto de cada fuente — recortado alrededor de lo que pregunta el usuario

Lo que nunca se toca: las reglas y la pregunta. Sin ellas no hay respuesta que recortar.

Contar tokens de verdad exigiría el tokenizador del modelo, que cambia con cada GGUF. Se
estima por caracteres y **se estima de más**: pasarse cuesta un poco de contexto,
quedarse corto cuesta la respuesta entera.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request

# Español con tildes en UTF-8: entre 3 y 4 caracteres por token según el tokenizador.
# Se usa 3.0 a propósito, para contar de más.
CHARS_PER_TOKEN = 3.0
# Cada mensaje del chat añade marcas de rol y separadores en la plantilla del modelo.
TOKENS_PER_MESSAGE = 8
# Colchón para la plantilla de chat entera (system prefix, BOS, cierres).
SAFETY_MARGIN = 96
# Por debajo de esto no hay prompt que valga; se manda lo mínimo y que el modelo responda.
MIN_PROMPT_TOKENS = 128
DEFAULT_CTX = 4096


def estimate_tokens(text: str) -> int:
    """Tokens que ocupará un texto, redondeando hacia arriba."""
    if not text:
        return 0
    return int(len(text) / CHARS_PER_TOKEN) + 1


def messages_tokens(messages: list[dict]) -> int:
    """Lo que ocupa una conversación entera, con la sobrecarga de cada turno."""
    total = 0
    for m in messages or []:
        total += estimate_tokens(m.get("content") or "") + TOKENS_PER_MESSAGE
    return total


def probe_ctx(base_url: str, timeout: float = 3.0) -> int | None:
    """El `n_ctx` que tiene cargado el servidor ahora mismo, o None si no contesta.

    Se pregunta en vez de suponerlo: el usuario puede haber cambiado de modelo, y cada
    GGUF trae el suyo.
    """
    url = f"{base_url.rstrip('/')}/props"
    try:
        with urllib.request.urlopen(url, timeout=timeout) as r:
            data = json.loads(r.read())
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, OSError, ValueError):
        return None
    if not isinstance(data, dict):
        return None
    for lugar in (data.get("default_generation_settings"), data):
        if isinstance(lugar, dict):
            n = lugar.get("n_ctx")
            if isinstance(n, int) and n > 0:
                return n
    return None


def prompt_budget(n_ctx: int, max_tokens: int) -> int:
    """Cuántos tokens puede ocupar el prompt dejando sitio para la respuesta."""
    if not n_ctx or n_ctx <= 0:
        n_ctx = DEFAULT_CTX
    libre = n_ctx - max(0, int(max_tokens or 0)) - SAFETY_MARGIN
    return max(MIN_PROMPT_TOKENS, libre)
