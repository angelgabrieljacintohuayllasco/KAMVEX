"""
Agente A — ensemble de predictores que propone candidatos, no una respuesta.

La idea de DASA es que Agente A recupera y Agente B redacta. Hasta ahora Agente A era
un solo recuperador (IVF-PQ) y su primer resultado se devolvía tal cual, así que
"dame más explicación" terminaba buscando la palabra *explicación* en el diccionario.

Aquí Agente A pasa a ser un **conjunto de predictores** que votan:

    SemanticPredictor   embeddings MiniLM + IVF-PQ (lo que ya hacía DASA)
    KeyPredictor        el nombre exacto mencionado en la pregunta (keyindex)
    TextPredictor       BM25 sobre el texto completo de los registros
    LexicalPredictor    solapamiento de palabras de contenido (BM25-lite sobre las claves)
    ExternalPredictor   cualquier predictor propio expuesto por HTTP (Laya, Kev, Von,
                        SemIf, NanoJev, jevlike…): POST {query, top_k} → [{key|text, score}]

Sus listas se funden con Reciprocal Rank Fusion, que no necesita que los scores estén
calibrados entre sí, y se premia el acuerdo: un registro propuesto por varios
predictores sube. El resultado es una lista de candidatos con su procedencia, que es
justo lo que Agente B necesita para elegir y responder.
"""

from __future__ import annotations

import array
import json
import math
import os
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from typing import Protocol

from grounding import content_terms, content_tokens
from keyindex import KeyIndex

RRF_K = 60           # constante estándar de Reciprocal Rank Fusion
AGREEMENT_BONUS = 0.15
DEFAULT_TOP_K = 5
# No todos los predictores merecen el mismo voto. El de claves acierta o no dice nada,
# así que pesa más; el léxico sobre claves es la pista más débil.
PREDICTOR_WEIGHTS = {"key": 3.0, "text": 1.4, "semantic": 1.0, "lexical": 0.7}
DEFAULT_WEIGHT = 1.0


@dataclass
class Candidate:
    """Un registro propuesto por uno o varios predictores."""
    key: str
    text: str
    score: float = 0.0                       # score fusionado (0-1, comparable)
    sources: dict[str, float] = field(default_factory=dict)   # predictor → score propio
    ranks: dict[str, int] = field(default_factory=dict)       # predictor → posición
    authority: bool = False                  # la pregunta nombró este registro entero

    @property
    def source_id(self) -> str:              # compatibilidad con los Fragment de DASA
        return self.key

    @property
    def agreement(self) -> int:
        return len(self.sources)

    def to_json(self) -> dict:
        out = {"text": self.text, "score": round(float(self.score), 4), "source_id": self.key,
               "predictors": {k: round(float(v), 4) for k, v in self.sources.items()},
               "agreement": self.agreement}
        if self.authority:
            out["authority"] = True
        return out


class Predictor(Protocol):
    name: str

    def predict(self, query: str, k: int) -> list[Candidate]:
        ...


# ── Predictores sobre el corpus local ───────────────────────────────────────

class SemanticPredictor:
    """El recuperador de DASA: embeddings + IVF-PQ (o el backend que tenga cargado)."""

    name = "semantic"

    def __init__(self, pipe):
        self.pipe = pipe

    def predict(self, query: str, k: int) -> list[Candidate]:
        out = []
        for f in self.pipe.agent_a.search(query)[:k]:
            out.append(Candidate(key=str(f.source_id or ""), text=f.text,
                                 sources={self.name: float(f.score)}))
        return out


class KeyPredictor:
    """El nombre propio mencionado en la pregunta ("Artículo 2", "efímero", "diabetes")."""

    name = "key"

    def __init__(self, index: KeyIndex, reader, record_to_text):
        self.index = index
        self.reader = reader
        self.record_to_text = record_to_text

    weight = PREDICTOR_WEIGHTS["key"]

    def predict(self, query: str, k: int) -> list[Candidate]:
        matcher = getattr(self.index, "match_kinds", None)
        hits = (matcher(query, limit=k) if callable(matcher)
                else [(key, "exact") for key in self.index.match(query, limit=k)])
        out = []
        for rank, (key, kind) in enumerate(hits):
            raw = self.reader.find(key)
            if not raw:
                continue
            try:
                record = json.loads(raw)
            except (json.JSONDecodeError, TypeError):
                record = {"text": str(raw)}
            # Solo el primer acierto exacto es autoritativo: si el usuario escribió
            # "Artículo 2", ese registro manda aunque otros predictores voten otra cosa.
            out.append(Candidate(key=key, text=self.record_to_text(record),
                                 sources={self.name: 1.0 - 0.05 * rank},
                                 authority=(rank == 0 and kind == "exact")))
        return out


class LexicalPredictor:
    """Solapamiento de palabras de contenido entre la pregunta y las claves del dataset.

    Complementa al semántico cuando la pregunta usa las palabras del registro pero no
    nombra la clave entera ("derechos fundamentales de la persona" → el capítulo).
    """

    name = "lexical"
    weight = PREDICTOR_WEIGHTS["lexical"]

    def __init__(self, index: KeyIndex, reader, record_to_text, max_keys: int = 20000):
        self.index = index
        self.reader = reader
        self.record_to_text = record_to_text
        self.keys = index.keys[:max_keys]
        self._terms = [(k, content_terms(k)) for k in self.keys]

    def predict(self, query: str, k: int) -> list[Candidate]:
        q = content_terms(query)
        if not q:
            return []
        scored: list[tuple[float, str]] = []
        for key, terms in self._terms:
            if not terms:
                continue
            common = len(q & terms)
            if not common:
                continue
            # Jaccard suavizado: premia cubrir la pregunta sin castigar claves largas
            scored.append((common / (len(q) + math.log1p(len(terms))), key))
        scored.sort(reverse=True)
        out = []
        for score, key in scored[:k]:
            raw = self.reader.find(key)
            if not raw:
                continue
            try:
                record = json.loads(raw)
            except (json.JSONDecodeError, TypeError):
                record = {"text": str(raw)}
            out.append(Candidate(key=key, text=self.record_to_text(record),
                                 sources={self.name: min(1.0, float(score))}))
        return out


class TextPredictor:
    """BM25 sobre el **texto** de los registros, no solo sobre sus claves.

    Es el predictor que faltaba. "explícame mis derechos" no nombra ningún registro y los
    embeddings devolvían artículos que solo hablan *de* derechos de refilón; BM25 sobre el
    contenido encuentra el artículo que repite la palabra, que es el que la responde.

    El índice invertido vive en `array('i')` (pares registro, frecuencia): unos pocos MB
    para 64 mil entradas, frente a las decenas que costaría en listas de tuplas.
    """

    name = "text"
    weight = PREDICTOR_WEIGHTS["text"]
    K1 = 1.2
    B = 0.75
    # BM25 castiga los registros largos porque asume que son palabrería. Un artículo que
    # enumera 32 derechos no es palabrería: es justo el que responde "explícame mis
    # derechos". Se topa el castigo al doble de la longitud media.
    LENGTH_CLAMP = 2.0
    MAX_RECORDS = 200_000

    def __init__(self, keys: list[str], records: list, record_to_text,
                 max_records: int = MAX_RECORDS):
        n = min(len(keys), len(records), max_records)
        self.keys = keys[:n]
        self.records = records[:n]
        self.record_to_text = record_to_text
        self.postings: dict[str, array.array] = {}
        self.lengths = array.array("i", [0]) * 0
        total = 0
        for i in range(n):
            counts: dict[str, int] = {}
            for tok in content_tokens(record_to_text(self.records[i])):
                counts[tok] = counts.get(tok, 0) + 1
            length = sum(counts.values())
            self.lengths.append(length)
            total += length
            for tok, tf in counts.items():
                post = self.postings.get(tok)
                if post is None:
                    post = self.postings[tok] = array.array("i")
                post.append(i)
                post.append(tf)
        self.n = n
        self.avgdl = (total / n) if n else 1.0

    @classmethod
    def from_dataset(cls, dataset_dir, record_to_text) -> "TextPredictor | None":
        """Construye el índice desde los ficheros del dataset, o None si no se puede."""
        keys_f, recs_f = dataset_dir / "keys.json", dataset_dir / "records.json"
        if not (keys_f.exists() and recs_f.exists()):
            return None
        try:
            keys = json.loads(keys_f.read_text(encoding="utf-8"))
            records = json.loads(recs_f.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError, MemoryError):
            return None
        if not isinstance(keys, list) or not isinstance(records, list) or not keys:
            return None
        return cls([str(k) for k in keys], records, record_to_text)

    def __len__(self) -> int:
        return self.n

    def bm25(self, terms) -> dict[int, float]:
        """Score BM25 crudo por registro. Separado de `predict` para poder medirlo."""
        scores: dict[int, float] = {}
        for term in set(terms):
            post = self.postings.get(term)
            if post is None:
                continue
            df = len(post) // 2
            idf = math.log(1.0 + (self.n - df + 0.5) / (df + 0.5))
            for j in range(0, len(post), 2):
                doc, tf = post[j], post[j + 1]
                dl = min(self.lengths[doc] or 1, self.avgdl * self.LENGTH_CLAMP)
                norm = tf + self.K1 * (1.0 - self.B + self.B * dl / self.avgdl)
                scores[doc] = scores.get(doc, 0.0) + idf * tf * (self.K1 + 1.0) / norm
        return scores

    def predict(self, query: str, k: int) -> list[Candidate]:
        terms = content_tokens(query)
        if not terms or not self.n:
            return []
        scores = self.bm25(terms)
        if not scores:
            return []
        best = sorted(scores.items(), key=lambda kv: (-kv[1], kv[0]))[:k]
        top = best[0][1] or 1.0
        return [Candidate(key=self.keys[doc], text=self.record_to_text(self.records[doc]),
                          sources={self.name: round(score / top, 4)})
                for doc, score in best]


class ExternalPredictor:
    """Un predictor propio detrás de HTTP.

    Contrato mínimo (`KAMVEX_PREDICTORS=nombre=url,otro=url`):

        POST url   {"query": "...", "top_k": 5, "dataset": "..."}
        200        {"candidates": [{"key": "...", "text": "...", "score": 0.93}, …]}

    `key` o `text`, al menos uno. Si solo llega `key`, el texto se lee del corpus.
    Pensado para enchufar Laya, Kev, Von, SemIf, NanoJev o jevlike sin tocar KAMVEX.
    """

    def __init__(self, name: str, url: str, reader=None, record_to_text=None, timeout: float = 20.0,
                 dataset: str = ""):
        self.name = name
        self.url = url
        self.reader = reader
        self.record_to_text = record_to_text
        self.timeout = timeout
        self.dataset = dataset
        self.last_error: str | None = None

    def predict(self, query: str, k: int) -> list[Candidate]:
        body = json.dumps({"query": query, "top_k": k, "dataset": self.dataset}).encode("utf-8")
        req = urllib.request.Request(self.url, data=body, headers={"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as r:
                data = json.loads(r.read())
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, OSError) as e:
            self.last_error = str(e)
            return []
        self.last_error = None
        items = data.get("candidates") if isinstance(data, dict) else data
        out = []
        for i, item in enumerate(items or []):
            if not isinstance(item, dict):
                continue
            key = str(item.get("key") or item.get("id") or "")
            text = str(item.get("text") or "")
            if not text and key and self.reader is not None:
                raw = self.reader.find(key)
                if raw:
                    try:
                        text = self.record_to_text(json.loads(raw))
                    except (json.JSONDecodeError, TypeError):
                        text = str(raw)
            if not text:
                continue
            score = float(item.get("score", 1.0 - 0.05 * i))
            out.append(Candidate(key=key or f"{self.name}-{i}", text=text, sources={self.name: score}))
        return out[:k]


def predictors_from_env(reader=None, record_to_text=None, dataset: str = "") -> list[ExternalPredictor]:
    """Lee KAMVEX_PREDICTORS ("laya=http://…/predict,kev=http://…/predict")."""
    raw = os.environ.get("KAMVEX_PREDICTORS", "").strip()
    out = []
    for part in raw.split(","):
        part = part.strip()
        if not part or "=" not in part:
            continue
        name, url = part.split("=", 1)
        name, url = name.strip(), url.strip()
        if name and url.startswith(("http://127.0.0.1", "http://localhost", "https://")):
            out.append(ExternalPredictor(name, url, reader, record_to_text, dataset=dataset))
    return out


# ── Fusión ──────────────────────────────────────────────────────────────────

def fuse(results: dict[str, list[Candidate]], top_k: int = DEFAULT_TOP_K,
         weights: dict[str, float] | None = None) -> list[Candidate]:
    """Reciprocal Rank Fusion ponderada + bonus por acuerdo entre predictores.

    RRF suma peso/(k + posición) por cada lista donde aparece el candidato, así que no
    hace falta que los scores de predictores distintos estén en la misma escala. El bonus
    por acuerdo levanta lo que varios proponen, la señal más fiable que tenemos.

    Un candidato **autoritativo** (la pregunta nombró el registro entero) va primero y con
    score 1.0. Sin esto, dos predictores flojos coincidiendo en otra cosa lo tapan: es lo
    que hacía que "explicame que es pene" contestara *pendiente*.
    """
    w = {**PREDICTOR_WEIGHTS, **(weights or {})}
    merged: dict[str, Candidate] = {}
    rrf: dict[str, float] = {}
    for name, items in results.items():
        weight = w.get(name, DEFAULT_WEIGHT)
        for rank, cand in enumerate(items):
            key = cand.key or cand.text[:80]
            existing = merged.get(key)
            if existing is None:
                existing = merged[key] = Candidate(key=cand.key, text=cand.text)
            elif len(cand.text) > len(existing.text):
                existing.text = cand.text          # quédate con el texto más completo
            existing.sources.update(cand.sources)
            existing.ranks[name] = rank
            existing.authority = existing.authority or cand.authority
            rrf[key] = rrf.get(key, 0.0) + weight / (RRF_K + rank + 1)

    if not merged:
        return []
    best = max(rrf.values()) or 1.0
    out = []
    for key, cand in merged.items():
        base = rrf[key] / best
        cand.score = min(1.0, base + AGREEMENT_BONUS * (cand.agreement - 1))
        if cand.authority:
            cand.score = 1.0
        out.append(cand)
    out.sort(key=lambda c: (not c.authority, -c.score, -c.agreement, c.key))
    return out[:top_k]


def run_ensemble(predictors: list, query: str, top_k: int = DEFAULT_TOP_K,
                 per_predictor: int | None = None) -> tuple[list[Candidate], dict]:
    """Ejecuta todos los predictores y funde. Devuelve (candidatos, diagnóstico)."""
    per = per_predictor or max(top_k, 5)
    results: dict[str, list[Candidate]] = {}
    info: dict[str, dict] = {}
    for p in predictors:
        try:
            items = p.predict(query, per)
        except Exception as e:  # noqa: BLE001 — un predictor caído no tumba el ensemble
            info[p.name] = {"n": 0, "error": str(e)[:160]}
            continue
        results[p.name] = items
        info[p.name] = {"n": len(items), "top": items[0].key if items else None}
        err = getattr(p, "last_error", None)
        if err:
            info[p.name]["error"] = err[:160]
    weights = {p.name: float(getattr(p, "weight", DEFAULT_WEIGHT)) for p in predictors}
    return fuse(results, top_k, weights), {"predictors": info}
