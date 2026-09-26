"""
Lexical key index — exact/near-exact record lookup that complements DASA's
semantic search.

Semantic embeddings are weak at identifiers ("Artículo 2" vs "Artículo 55") and at
rare lemmas. Every KAMVEX dataset ships `keys.json` (record keys in order), so we
can spot record keys mentioned verbatim in the question (word n-grams, accents and
case ignored, 1-edit typos for single words) and pull those records straight from
the SHARD store with a top score. The result is merged in front of the semantic
candidates: retrieval becomes exact when the user names the thing.
"""

from __future__ import annotations

import json
import re
import unicodedata
from pathlib import Path

MAX_NGRAM = 6
FUZZY_MIN_LEN = 5
KEY_HIT_SCORE = 1.0
# Un diccionario tiene entradas para "y", "de" o "una". Sin esto, "y el artículo 35?"
# coincide con la conjunción *y* y esa entrada gana con score 1.0.
STOPWORD_KEYS = set("""
a al algo alguna algunas alguno algunos ante antes aqui asi aun aunque cada como con contra cual
cuales cuando cuanto de del desde donde dos e el ella ellas ellos en entre era eran es esa esas
ese eso esos esta estas este esto estos fue ha hay la las le les lo los mas me mi mis mucho muy
nada ni no nos o os otra otras otro otros para pero poco por porque pues que quien se sea ser si
sin so sobre solo son su sus tal tan tanto te ti tu tus un una unas uno unos ya yo
""".split())
# Solo se ignoran si la pregunta es más larga que la propia clave: preguntar literalmente
# "¿qué significa 'de'?" sí debe encontrar la preposición.
MIN_QUERY_WORDS_TO_IGNORE_STOPWORDS = 3


def _normalize(text: str) -> str:
    text = unicodedata.normalize("NFD", text.lower())
    text = "".join(c for c in text if unicodedata.category(c) != "Mn")
    return " ".join(re.findall(r"[a-z0-9ñ]+", text))


def _lev1(a: str, b: str) -> bool:
    """True if Levenshtein distance ≤ 1 (O(n))."""
    if a == b:
        return True
    la, lb = len(a), len(b)
    if abs(la - lb) > 1:
        return False
    if la == lb:
        return sum(x != y for x, y in zip(a, b)) == 1
    if la < lb:
        a, b, la, lb = b, a, lb, la
    i = 0
    while i < lb and a[i] == b[i]:
        i += 1
    return a[i + 1:] == b[i:]


class KeyIndex:
    """Normalized record keys of one dataset, with n-gram and fuzzy lookup."""

    def __init__(self, keys: list[str]):
        self.keys = keys
        self._by_norm: dict[str, list[str]] = {}
        self._by_len: dict[int, list[tuple[str, str]]] = {}
        for k in keys:
            base = k.split("#")[0]           # KAMVEX disambiguates duplicates as key#n
            n = _normalize(base)
            if not n:
                continue
            self._by_norm.setdefault(n, []).append(k)
            self._by_len.setdefault(len(n), []).append((n, k))
        self._single = {n: ks for n, ks in self._by_norm.items() if " " not in n and len(n) >= FUZZY_MIN_LEN}

    @classmethod
    def load(cls, dataset_dir: Path) -> "KeyIndex | None":
        for name in ("keys.json", "embedding_keys.json"):
            f = dataset_dir / name
            if f.exists():
                try:
                    keys = json.loads(f.read_text(encoding="utf-8"))
                    if isinstance(keys, list) and keys:
                        return cls([str(k) for k in keys])
                except (json.JSONDecodeError, OSError):
                    continue
        return None

    def __len__(self) -> int:
        return len(self.keys)

    def match(self, query: str, limit: int = 3) -> list[str]:
        """Record keys named in the query, best first."""
        return [k for k, _kind in self.match_kinds(query, limit)]

    def match_kinds(self, query: str, limit: int = 3) -> list[tuple[str, str]]:
        """Como `match`, pero diciendo **cómo** coincidió cada clave.

        `exact` = la pregunta contiene la clave entera ("Artículo 2"), y eso es tan fuerte
        que manda sobre cualquier otro predictor. `prefix` = la clave empieza por el
        término ("departamento de amazonas" → "… (Perú)"). `fuzzy` = a una letra de
        distancia (efimero → efémero). Los dos últimos son pistas, no certezas.

        Longest n-gram wins; among ties, exact key equality beats prefix matches and
        shorter keys beat longer ones.
        """
        words = _normalize(query).split()
        if not words:
            return []
        skip_stopwords = len(words) >= MIN_QUERY_WORDS_TO_IGNORE_STOPWORDS
        scored: dict[str, tuple[int, int, int]] = {}
        for n in range(min(MAX_NGRAM, len(words)), 0, -1):
            for i in range(0, len(words) - n + 1):
                gram = " ".join(words[i:i + n])
                if skip_stopwords and n == 1 and gram in STOPWORD_KEYS:
                    continue
                exact = self._by_norm.get(gram, [])
                for k in exact:
                    scored.setdefault(k, (n, 0, len(gram)))
                # Prefix matches only when the term itself is not a record ("departamento de
                # amazonas" → "… (Perú)"); otherwise "diabetes" would drag in "diabetes tipo 2".
                if not exact and (n >= 2 or len(gram) >= FUZZY_MIN_LEN):
                    # prefix matches: "departamento de amazonas" → "departamento de amazonas (peru)"
                    for length, items in self._by_len.items():
                        if length <= len(gram) or length > len(gram) + 40:
                            continue
                        for norm, k in items:
                            if norm.startswith(gram + " ") or norm.startswith(gram + "("):
                                scored.setdefault(k, (n, 1, length))
            if scored and n >= 2:
                break
        if not scored:
            # fuzzy single word: the extracted term may be misspelled or accented differently
            for w in words:
                if len(w) < FUZZY_MIN_LEN or (skip_stopwords and w in STOPWORD_KEYS):
                    continue
                for norm, ks in self._single.items():
                    if _lev1(w, norm):
                        for k in ks:
                            scored.setdefault(k, (1, 2, len(norm)))
        ranked = sorted(scored.items(), key=lambda kv: (-kv[1][0], kv[1][1], kv[1][2], kv[0]))
        kinds = ("exact", "prefix", "fuzzy")
        return [(k, kinds[v[1]]) for k, v in ranked[:limit]]
