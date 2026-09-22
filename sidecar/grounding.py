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
termino terminos refiere refieren significa significan significado consiste consisten describe define
denota expresion palabra palabras concepto indica indican utiliza utilizan usa usan tipo tipos forma
formas manera accion efecto persona personas cosa cosas hace hacer puede pueden tiene tienen esta estan
ejemplo general especialmente principalmente ademas asi decir dice dicen sobre acerca respecto relacion
relacionado relacionada caracteriza caracterizan conocido conocida llamado llamada denominado denominada
""".split())

# Grounded mode context budget: small CPU models spend most of the time on prompt
# processing and stop paying attention to the middle of a long passage, so records are
# reduced to the sentences that actually answer the question.
GROUNDED_MAX_FRAGMENTS = 3
GROUNDED_MAX_CHARS = 900
SENTENCE_RE = re.compile(r"(?<=[.!?:])\s+|\n+")


def split_sentences(text: str) -> list[str]:
    return [s.strip() for s in SENTENCE_RE.split(text) if s.strip()]


def focus_text(query: str, text: str, max_chars: int = GROUNDED_MAX_CHARS) -> str:
    """Keep the sentences that answer `query`, in their original order.

    A 1.5B model reading 2 000 characters often misses "Su capital es Chachapoyas" in
    sentence two. Scoring sentences by overlap with the question and dropping the rest
    puts the answer where the model actually looks — and makes the prompt much cheaper.
    The first sentence is always kept: it says what the record is about.
    """
    if len(text) <= max_chars:
        return text
    sentences = split_sentences(text)
    if len(sentences) <= 1:
        return text[:max_chars]
    q_terms = content_terms(query)
    scored: list[tuple[float, int]] = []
    for i, s in enumerate(sentences):
        terms = content_terms(s)
        overlap = len(q_terms & terms) / (len(q_terms) or 1)
        # tiny positional prior: earlier sentences are usually the definition
        scored.append((overlap + max(0.0, 0.15 - i * 0.01), i))
    scored.sort(reverse=True)

    keep = {0}
    used = len(sentences[0])
    for _, i in scored:
        if i in keep:
            continue
        if used + len(sentences[i]) + 1 > max_chars:
            continue
        keep.add(i)
        used += len(sentences[i]) + 1
    return " ".join(sentences[i] for i in sorted(keep))


def trim_fragments(fragments, query: str = "", max_fragments: int = GROUNDED_MAX_FRAGMENTS,
                   max_chars: int = GROUNDED_MAX_CHARS):
    """Top fragments, each reduced to the sentences relevant to `query`."""
    out = []
    for f in fragments[:max_fragments]:
        text = getattr(f, "text", str(f))
        text = focus_text(query, text, max_chars) if query else text[:max_chars]
        out.append(type("Frag", (), {"text": text, "score": getattr(f, "score", 0.0),
                                     "source_id": getattr(f, "source_id", None)})())
    return out

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


NOT_COVERED_ES = "La información disponible no cubre este tema."
NOT_COVERED_EN = "The available information does not cover this topic."

# Small models (1–3B) read a strict "say you don't know" rule as an easy way out and
# refuse even when the answer is right there. A worked example fixes that: it shows the
# expected behaviour (extract and answer) and keeps the escape hatch for the real case.
_EXAMPLE_ES = [
    {"role": "user", "content": (
        "CONTEXTO:\n[1] Tacna: Tacna es una ciudad del sur del Perú, capital del departamento "
        "de Tacna. Fue fundada en 1855 y tiene un clima desértico.\n\nPREGUNTA: ¿De qué departamento es capital Tacna?")},
    {"role": "assistant", "content": "Tacna es la capital del departamento de Tacna."},
    {"role": "user", "content": (
        "CONTEXTO:\n[1] Tacna: Tacna es una ciudad del sur del Perú, capital del departamento "
        "de Tacna. Fue fundada en 1855 y tiene un clima desértico.\n\nPREGUNTA: ¿Cuántos habitantes tiene Tacna?")},
    {"role": "assistant", "content": NOT_COVERED_ES},
]
_EXAMPLE_EN = [
    {"role": "user", "content": (
        "CONTEXT:\n[1] Tacna: Tacna is a city in southern Peru, capital of the Tacna Region. "
        "It was founded in 1855.\n\nQUESTION: Which region is Tacna the capital of?")},
    {"role": "assistant", "content": "Tacna is the capital of the Tacna Region."},
    {"role": "user", "content": (
        "CONTEXT:\n[1] Tacna: Tacna is a city in southern Peru, capital of the Tacna Region. "
        "It was founded in 1855.\n\nQUESTION: How many people live in Tacna?")},
    {"role": "assistant", "content": NOT_COVERED_EN},
]


def grounded_messages(query: str, fragments) -> list[dict]:
    """Strict formatter prompt: only the CONTEXT, no preamble, same language as the question."""
    lang = _language(query)
    context = "\n".join(f"[{i + 1}] {getattr(f, 'text', str(f))}" for i, f in enumerate(fragments))
    if lang == "en":
        system = (
            "You answer questions using ONLY the CONTEXT you are given.\n"
            "1) If the CONTEXT contains the answer, state it directly, in one or two sentences, "
            "reusing the CONTEXT's own wording.\n"
            "2) Never add facts, figures, examples or names that are not in the CONTEXT.\n"
            f"3) Only when the CONTEXT says nothing about what is asked, reply exactly: '{NOT_COVERED_EN}'\n"
            "4) No preamble, no 'according to the context', no lists unless the CONTEXT has one."
        )
        example = _EXAMPLE_EN
        user = f"CONTEXT:\n{context}\n\nQUESTION: {query}"
    else:
        system = (
            "Respondes preguntas usando SOLO el CONTEXTO que se te da.\n"
            "1) Si el CONTEXTO contiene la respuesta, dila directamente, en una o dos oraciones, "
            "reutilizando las palabras del propio CONTEXTO.\n"
            "2) Nunca añadas datos, cifras, ejemplos ni nombres que no estén en el CONTEXTO.\n"
            f"3) Solo cuando el CONTEXTO no diga nada sobre lo que se pregunta, responde exactamente: '{NOT_COVERED_ES}'\n"
            "4) Sin preámbulos, sin 'según el contexto', en español."
        )
        example = _EXAMPLE_ES
        user = f"CONTEXTO:\n{context}\n\nPREGUNTA: {query}"
    return [{"role": "system", "content": system}, *example, {"role": "user", "content": user}]
