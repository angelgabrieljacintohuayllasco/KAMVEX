"""
Grounding helpers that make Agent B answers more exact and more deterministic
without touching DASA:

- `exact_definition_answer`: for "¿qué es X?"-style questions whose term matches a
  retrieved record key, answer with that record's own text (no rewriting at all).
- `grounded_messages`: KAMVEX's strict formatter prompt (language-aware, no preamble).
- `coverage`: lexical guardrail — share of the LLM answer's content words that appear
  in the retrieved fragments. Anything the corpus does not contain is a hallucination
  candidate; callers fall back to the deterministic answer when coverage is low.
"""

from __future__ import annotations

import re
import unicodedata

MIN_COVERAGE = 0.85          # below this a grounded answer is rejected
STEM_LEN = 5                 # crude inflection tolerance: derecho/derechos → "derec"
DETERMINISTIC_SEED = 42

_STOPWORDS = set("""
a al algo alguna algunas alguno algunos ante antes aquel aquella aquellas aquellos aqui asi aun aunque
cada casi como con contra cual cuales cualquier cuando cuanta cuantas cuanto cuantos de del desde donde
dos durante e el ella ellas ellos en entre era eran es esa esas ese eso esos esta estaba estaban estamos
estan estar estas este esto estos fue fueron ha habia haber hace hacia han hasta hay la las le les lo
los mas me mi mia mias mientras mio mios mis mucho muchos muy nada ni no nos nosotros nuestra nuestras
nuestro nuestros o os otra otras otro otros para pero poco por porque pues que quien quienes se sea sean
segun ser si sido siempre sin sino sobre solo son su sus tal tambien tan tanto te tener tiene tienen toda
todas todo todos tras tu tus un una unas uno unos usted ustedes vez y ya yo
the a an and or of to in on for with is are was were be been this that these those it its as by at from
according information available contexto pregunta respuesta texto informacion disponible cubre tema
""".split())

_QUERY_PREFIX_RE = re.compile(
    r"^(?:[¿]?\s*(?:qu[eé]\s+(?:significa|es|son|quiere\s+decir|dice|establece)\s+"
    r"(?:la\s+|el\s+|los\s+|las\s+|un\s+|una\s+)?|defin[ei]\S*\s+(?:de\s+)?|significado\s+de\s+|"
    r"what\s+(?:is|are|does)\s+(?:a\s+|an\s+|the\s+)?|define\s+))",
    re.IGNORECASE,
)


def normalize(text: str) -> str:
    text = unicodedata.normalize("NFD", text.lower())
    return "".join(c for c in text if unicodedata.category(c) != "Mn")


def tokens(text: str) -> list[str]:
    return re.findall(r"[a-z0-9ñ]+", normalize(text))


def stem(tok: str) -> str:
    return tok[:STEM_LEN] if len(tok) > STEM_LEN else tok


def content_terms(text: str) -> set[str]:
    """Stemmed content words: no stopwords, no very short tokens (numbers are kept)."""
    out = set()
    for tok in tokens(text):
        if tok in _STOPWORDS:
            continue
        if len(tok) < 4 and not tok.isdigit():
            continue
        out.add(stem(tok))
    return out


def coverage(answer: str, fragments) -> tuple[float, list[str]]:
    """Fraction of the answer's content terms present in the fragments (+ the missing ones)."""
    corpus: set[str] = set()
    for f in fragments:
        corpus |= content_terms(getattr(f, "text", str(f)))
        sid = getattr(f, "source_id", None)
        if sid:
            corpus |= content_terms(str(sid))
    terms = content_terms(answer)
    if not terms:
        return 1.0, []
    missing = sorted(t for t in terms if t not in corpus)
    return round(1.0 - len(missing) / len(terms), 3), missing


def extract_term(query: str) -> str:
    """'¿qué es huevo?' → 'huevo'; 'define serendipia' → 'serendipia'."""
    cleaned = _QUERY_PREFIX_RE.sub("", query.strip())
    term = re.split(r"[?¿!.,;:]", cleaned)[0].strip().strip("'\"«»")
    return term


def exact_definition_answer(query: str, fragments) -> str | None:
    """If the question names a record key exactly, return that record's text verbatim."""
    term = normalize(extract_term(query))
    if len(term) < 2:
        return None
    for f in fragments:
        sid = getattr(f, "source_id", None) or ""
        key = normalize(str(sid).split("#")[0])
        text = getattr(f, "text", "")
        if key and key == term:
            return text
        head = normalize(text.split(":")[0]) if ":" in text else ""
        if head and head == term:
            return text
    return None


def _language(query: str) -> str:
    q = normalize(query)
    en_hits = sum(w in q.split() for w in ("what", "which", "how", "does", "the", "is", "are"))
    es_hits = sum(w in q.split() for w in ("que", "cual", "como", "es", "son", "el", "la", "los", "de"))
    return "en" if en_hits > es_hits else "es"


def grounded_messages(query: str, fragments) -> list[dict]:
    """Strict formatter prompt: only the CONTEXT, no preamble, same language as the question."""
    lang = _language(query)
    context = "\n".join(f"[{i + 1}] {getattr(f, 'text', str(f))}" for i, f in enumerate(fragments))
    if lang == "en":
        system = (
            "You are a text formatter. Answer the QUESTION using ONLY the CONTEXT.\n"
            "Rules: 1) Never add facts, examples or words that are not in the CONTEXT. "
            "2) If the CONTEXT does not answer the question reply exactly: "
            "'The available information does not cover this topic.' "
            "3) Be direct: no preamble, no 'according to the context'. 4) At most 3 sentences."
        )
        user = f"CONTEXT:\n{context}\n\nQUESTION: {query}"
    else:
        system = (
            "Eres un reformateador de texto. Responde la PREGUNTA usando SOLO el CONTEXTO.\n"
            "Reglas: 1) Nunca añadas datos, ejemplos ni palabras que no estén en el CONTEXTO. "
            "2) Si el CONTEXTO no responde la pregunta, contesta exactamente: "
            "'La información disponible no cubre este tema.' "
            "3) Sé directo: sin preámbulos ni 'según el contexto'. 4) Máximo 3 oraciones, en español."
        )
        user = f"CONTEXTO:\n{context}\n\nPREGUNTA: {query}"
    return [{"role": "system", "content": system}, {"role": "user", "content": user}]
