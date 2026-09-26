"""
Los modelos de decisión: dada la pregunta y los candidatos, dicen cuál responde.

Entre el Agente A y el Agente B falta un paso. Agente A propone varios candidatos ordenados
por recuperación, que es una señal distinta de «cuál contesta la pregunta». Agente B, si es
un modelo pequeño, a veces se queda con el primero aunque el bueno sea el tercero.

Esa es exactamente la tarea de la familia de modelos de decisión abiertos —Laya, Kev, Von,
SemIf, NanoJev— y del entrenador jevlike. Ninguno recupera: todos responden la misma
pregunta tipada, *Choice*: dado un estado y un conjunto de opciones, devuelven una
probabilidad por opción en una sola pasada, sin generar texto.

Aquí hay dos implementaciones de ese contrato:

    LogitChooser     la técnica de SemIf con el llama-server que ya corre: se lee la
                     probabilidad de las etiquetas «1», «2», «3»… en la siguiente posición.
                     Una pasada, sin generar, sin dependencias nuevas, en CPU.
    ExternalChooser  cualquiera de esos modelos detrás de HTTP, con su propio contrato.

Referencias: Laya (convaiinnovations/laya, ModernBERT-large, Apache-2.0),
SemIf (TheoLeeCJ/SemIf-OpenJev), NanoJev (TianyuCodings/NanoJev, Qwen3-0.6B + cabezas
tipadas), Kev (adaptadores LoRA sobre Qwen3.5 que sirven /v1/systemone).
"""

from __future__ import annotations

import json
import math
import os
import re
import urllib.error
import urllib.request
from dataclasses import dataclass, field

from grounding import focus_text

MAX_OPTIONS = 8
OPTION_CHARS = 700
# Un candidato tiene que ganar por algo, no por ruido numérico.
MIN_MARGIN = 0.05


@dataclass
class Decision:
    """Lo que dice un elector sobre el conjunto de candidatos."""

    scores: list[float]                       # una probabilidad por candidato, suman 1
    source: str = ""
    error: str | None = None
    per_chooser: dict[str, list[float]] = field(default_factory=dict)

    @property
    def picked(self) -> int | None:
        if not self.scores:
            return None
        best = max(range(len(self.scores)), key=lambda i: self.scores[i])
        rest = [s for i, s in enumerate(self.scores) if i != best]
        if rest and self.scores[best] - max(rest) < MIN_MARGIN:
            return None                       # empate: que decida el orden del Agente A
        return best

    def to_json(self) -> dict:
        out = {"source": self.source, "picked": self.picked,
               "scores": [round(s, 4) for s in self.scores]}
        if self.per_chooser:
            out["per_chooser"] = {k: [round(s, 4) for s in v] for k, v in self.per_chooser.items()}
        if self.error:
            out["error"] = self.error
        return out


# El final del prompt decide si el siguiente token es un dígito. Medido con Gemma 2 2B:
# terminar en «…es la número» hace que el modelo quiera escribir «:» o «**», y no aparece
# ni un dígito entre los 40 candidatos más probables. Terminar en «Opción correcta: » deja
# el «2» a -0.1 y el segundo a -7.2.
COMPLETION_SUFFIX = "\n\nOpción correcta: "


def options_prompt(query: str, candidates, chars: int = OPTION_CHARS) -> str:
    """El estado y las opciones numeradas, pidiendo solo el número."""
    lines = ["Elige la opción que responde la pregunta.", "", f"PREGUNTA: {query}", "", "OPCIONES:"]
    for i, c in enumerate(candidates[:MAX_OPTIONS], start=1):
        text = getattr(c, "text", str(c))
        if len(text) > chars:
            text = focus_text(query, text, chars)
        lines.append(f"{i}. {text}")
    lines += ["", "Responde solo con el número de la opción correcta."]
    return "\n".join(lines)


def _softmax(logprobs: dict[int, float]) -> list[float]:
    """Normaliza sobre las etiquetas válidas; las que el modelo no propuso valen 0."""
    if not logprobs:
        return []
    top = max(logprobs.values())
    exps = {i: math.exp(lp - top) for i, lp in logprobs.items()}
    total = sum(exps.values()) or 1.0
    return [exps.get(i, 0.0) / total for i in range(max(logprobs) + 1)]


class LogitChooser:
    """La técnica de SemIf sobre llama-server: una pasada, sin generar texto.

    En vez de pedirle al modelo que escriba «la opción 2» y luego parsearlo, se lee
    directamente qué probabilidad le da a cada etiqueta en la siguiente posición. Es
    determinista, cuesta una pasada y no depende de que el modelo sepa obedecer un formato.
    """

    name = "logit"

    def __init__(self, base_url: str, timeout: float = 60.0, n_probs: int = 20):
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.n_probs = n_probs
        self.last_error: str | None = None

    def choose(self, query: str, candidates) -> list[float]:
        n = min(len(candidates), MAX_OPTIONS)
        if n < 2:
            return [1.0] * n
        prompt = options_prompt(query, candidates)
        # Primero la ruta de chat: aplica la plantilla del modelo, y un modelo instruct al
        # que le piden un número pone el dígito en la primera posición con mucho margen.
        scores = self._chat(prompt, n)
        if scores:
            return scores
        # Si el servidor no da logprobs por esa vía, la ruta cruda con el final que fuerza
        # un dígito. Es la misma técnica, sin plantilla.
        return self._raw(prompt, n)

    def _post(self, path: str, body: dict):
        data = json.dumps(body).encode("utf-8")
        req = urllib.request.Request(f"{self.base_url}{path}", data=data,
                                     headers={"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as r:
                out = json.loads(r.read())
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, OSError) as e:
            self.last_error = str(e)[:160]
            return None
        self.last_error = None
        return out

    def _chat(self, prompt: str, n: int) -> list[float]:
        data = self._post("/v1/chat/completions", {
            "messages": [{"role": "user", "content": prompt}],
            "max_tokens": 1, "temperature": 0.0,
            "logprobs": True, "top_logprobs": self.n_probs,
        })
        if not data:
            return []
        try:
            content = ((data.get("choices") or [{}])[0].get("logprobs") or {}).get("content") or []
        except (AttributeError, IndexError, TypeError):
            return []
        if not content:
            return []
        return self._labels_from(content[0].get("top_logprobs") or [], n)

    def _raw(self, prompt: str, n: int) -> list[float]:
        data = self._post("/completion", {
            "prompt": prompt + COMPLETION_SUFFIX,
            "n_predict": 1, "n_probs": self.n_probs,
            "temperature": 0.0, "cache_prompt": True,
        })
        if not data:
            return []
        return self._read_labels(data, n)

    @classmethod
    def _read_labels(cls, data: dict, n: int) -> list[float]:
        probs = data.get("completion_probabilities") or []
        if not probs:
            return []
        top = (probs[0] or {}).get("top_logprobs") or (probs[0] or {}).get("probs") or []
        return cls._labels_from(top, n)

    @staticmethod
    def _labels_from(top, n: int) -> list[float]:
        """De la lista de tokens más probables a una distribución sobre las opciones."""
        best: dict[int, float] = {}
        for entry in top or []:
            if not isinstance(entry, dict):
                continue
            token = str(entry.get("token", "")).strip()
            if not token.isdigit():
                continue
            idx = int(token) - 1                      # las etiquetas empiezan en 1
            if not 0 <= idx < n:
                continue
            lp = entry.get("logprob")
            if lp is None:
                p = entry.get("prob")
                lp = math.log(p) if p and p > 0 else None
            if lp is None:
                continue
            # El mismo número puede llegar como "2" y como " 2": vale el más probable.
            if idx not in best or lp > best[idx]:
                best[idx] = float(lp)
        if not best:
            return []
        scores = _softmax(best)
        return (scores + [0.0] * n)[:n]


class ExternalChooser:
    """Un modelo de decisión propio detrás de HTTP.

    Contrato (`KAMVEX_CHOOSERS=laya=http://127.0.0.1:9101/decide,...`):

        POST url   {"state": "<pregunta>", "question": "…", "options": [{"id": "1", "text": "…"}]}
        200        {"scores": {"1": 0.81, "2": 0.19}}        ← Laya, SemIf: distribución
                   {"choice": "1"}                            ← solo la elegida, también vale
                   {"answers": {"choice": {"choice": "1", "probs": {...}}}}   ← forma de Laya

    Pensado para Laya, Kev, Von, SemIf y NanoJev sin tocar KAMVEX. Un elector caído no
    rompe nada: se anota el error y deciden los demás.
    """

    def __init__(self, name: str, url: str, timeout: float = 30.0,
                 instructions: str = "¿Cuál de estas opciones responde la pregunta?"):
        self.name = name
        self.url = url
        self.timeout = timeout
        self.instructions = instructions
        self.last_error: str | None = None

    def choose(self, query: str, candidates) -> list[float]:
        n = min(len(candidates), MAX_OPTIONS)
        if n < 2:
            return [1.0] * n
        options = []
        for i, c in enumerate(candidates[:n], start=1):
            text = getattr(c, "text", str(c))
            if len(text) > OPTION_CHARS:
                text = focus_text(query, text, OPTION_CHARS)
            options.append({"id": str(i), "text": text,
                            "key": str(getattr(c, "key", "") or "")})
        body = json.dumps({"state": query, "question": self.instructions,
                           "type": "choice", "options": options}).encode("utf-8")
        req = urllib.request.Request(self.url, data=body,
                                     headers={"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as r:
                data = json.loads(r.read())
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, OSError) as e:
            self.last_error = str(e)[:160]
            return []
        self.last_error = None
        return self._read(data, n)

    @staticmethod
    def _read(data, n: int) -> list[float]:
        if not isinstance(data, dict):
            return []
        scores = data.get("scores") or data.get("probs") or data.get("distribution")
        # Forma de Laya: answers.<pregunta>.choice / .probs
        if scores is None:
            answers = data.get("answers")
            if isinstance(answers, dict):
                for value in answers.values():
                    if isinstance(value, dict):
                        scores = value.get("probs") or value.get("scores")
                        if scores is None and value.get("choice") is not None:
                            data = {"choice": value["choice"]}
                        break
        if isinstance(scores, dict):
            out = [float(scores.get(str(i + 1), 0.0) or 0.0) for i in range(n)]
        elif isinstance(scores, list):
            out = [float(x or 0.0) for x in scores[:n]]
        else:
            choice = data.get("choice", data.get("picked"))
            idx = _label_index(choice, n)
            if idx is None:
                return []
            out = [1.0 if i == idx else 0.0 for i in range(n)]
        total = sum(out)
        return [x / total for x in out] if total > 0 else []


def _label_index(choice, n: int) -> int | None:
    """«2», 2, «opción 2» → 1. Devuelve None si no se reconoce."""
    if choice is None:
        return None
    if isinstance(choice, bool):
        return None
    if isinstance(choice, int):
        idx = choice - 1
        return idx if 0 <= idx < n else None
    m = re.search(r"\d+", str(choice))
    if not m:
        return None
    idx = int(m.group()) - 1
    return idx if 0 <= idx < n else None


def choosers_from_env() -> list[ExternalChooser]:
    """Lee KAMVEX_CHOOSERS ("laya=http://…/decide,von=http://…/decide")."""
    raw = os.environ.get("KAMVEX_CHOOSERS", "").strip()
    out = []
    for part in raw.split(","):
        part = part.strip()
        if not part or "=" not in part:
            continue
        name, url = part.split("=", 1)
        name, url = name.strip(), url.strip()
        if name and url.startswith(("http://127.0.0.1", "http://localhost", "https://")):
            out.append(ExternalChooser(name, url))
    return out


def decide(query: str, candidates, choosers: list) -> Decision:
    """Ejecuta los electores y promedia sus distribuciones.

    Promediar y no votar por mayoría: una distribución dice *cuánto* prefiere cada uno, y
    un elector inseguro no debe pesar igual que uno convencido. Un elector que falla o
    devuelve basura sale del promedio en vez de contaminar el resultado.
    """
    n = min(len(candidates), MAX_OPTIONS)
    if n < 2 or not choosers:
        return Decision(scores=[], source="")
    per: dict[str, list[float]] = {}
    errors: list[str] = []
    for ch in choosers:
        try:
            scores = ch.choose(query, candidates)
        except Exception as e:  # noqa: BLE001 — un elector roto no tumba la respuesta
            errors.append(f"{ch.name}: {str(e)[:80]}")
            continue
        err = getattr(ch, "last_error", None)
        if err:
            errors.append(f"{ch.name}: {err}")
        if scores and len(scores) >= n and sum(scores) > 0:
            per[ch.name] = scores[:n]
    if not per:
        return Decision(scores=[], source="", error="; ".join(errors)[:200] or None)
    avg = [sum(s[i] for s in per.values()) / len(per) for i in range(n)]
    return Decision(scores=avg, source="+".join(per), per_chooser=per,
                    error="; ".join(errors)[:200] or None)


def reorder(candidates, decision: Decision):
    """Los candidatos con el elegido delante, conservando el resto del orden del Agente A."""
    picked = decision.picked
    if picked is None or picked >= len(candidates):
        return candidates
    return [candidates[picked]] + [c for i, c in enumerate(candidates) if i != picked]
