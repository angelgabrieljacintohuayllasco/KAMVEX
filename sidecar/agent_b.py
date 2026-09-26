"""
Agente B — el LLM que lee las predicciones de Agente A y le responde al usuario.

Agente A no responde: propone candidatos. Agente B hace tres cosas que un recuperador
no puede hacer y que son justo las que fallaban:

1. **Resolver la pregunta contra la conversación.** "dame más explicación" no es una
   consulta nueva: hay que reescribirla contra lo último que se habló antes de buscar,
   o el recuperador termina devolviendo la entrada del diccionario para *explicación*.
2. **Elegir entre los candidatos.** El ensemble propone varios; el modelo decide cuál
   responde la pregunta (o que ninguno lo hace).
3. **Redactar.** Parafrasear, resumir o ampliar usando solo lo que dicen los candidatos,
   en el nivel de detalle que pidió el usuario.

Todo lo que produce pasa después por el guardarraíl léxico de `grounding.py`.
"""

from __future__ import annotations

import re
import unicodedata

from grounding import content_terms, focus_text, normalize

# Signos y comillas de apertura: "¿qué más?" empieza por "¿", no por la palabra.
_LEAD_RE = re.compile(r"^[\s¿¡\"'“‘(\[]+")
# Preguntas que piden algo pero pueden no traer sujeto propio.
_FOLLOWUP_RE = re.compile(
    r"^(?:y\s|pero\s|entonces\s)?\s*(?:"
    r"dame|dime|expl[ií]ca\w*|ampl[ií]a\w*|detall\w*|resum\w*|resúme|continu\w*|sigue|"
    r"otra vez|de nuevo|mas\b|más\b|otro ejemplo|ponme un ejemplo|"
    r"y\s+(?:el|la|los|las)\b|que\s+mas|qué\s+más"
    r")",
    re.IGNORECASE,
)
_PRONOUN_RE = re.compile(r"\b(eso|esto|aquello|lo mismo|ese|esa|ello|su significado|al respecto)\b",
                         re.IGNORECASE)
# Pistas de que el usuario quiere más de lo que ya se le dio.
_MORE_RE = re.compile(r"\b(mas|más|amplia|amplía|detall\w*|larga|largo|profund\w*|extens\w*|"
                      r"explica\w*|ejemplos?|resum\w*)\b", re.IGNORECASE)
# Vocabulario de "pídeme más": estas palabras no son un tema, son la petición.
_META_RE = re.compile(
    r"^(?:dame|dime|hazme|ponme|explica\w*|amplia\w*|detall\w*|resum\w*|continu\w*|sigue|"
    r"aclara\w*|desarrolla\w*|especifica\w*|otra|otro|otras|otros|vez|nuevo|nueva|"
    r"mas|larga|largo|corta|corto|profund\w*|extens\w*|ejemplo\w*|explicacion\w*|"
    r"informacion|respuesta|favor|porfavor|mejor|completa|completo|breve|mucho|muy|bien|"
    r"algo|todo|toda|sobre|acerca|tema|punto|eso|esto|aquello|palabra|significado|"
    r"pregunta|anterior|dicho|antes|ahora|entonces|pero|tambien)$")
# Palabras de función: nunca son el tema de la pregunta.
_GENERIC = {"que", "cual", "cuales", "como", "cuando", "donde", "quien", "para", "por", "con",
            "sin", "los", "las", "del", "una", "uno", "unos", "unas", "este", "esta", "estos",
            "estas", "ese", "esa", "esos", "esas", "mis", "sus", "tus", "nos", "les", "muy",
            "segun", "desde", "hasta", "entre", "sobre", "entonces", "pues"}

MAX_CANDIDATES_IN_PROMPT = 4
CANDIDATE_CHARS = 900
HISTORY_TURNS = 6


def is_followup(query: str) -> bool:
    """¿La pregunta depende del turno anterior para tener sentido?

    Depende si pide algo ("dame", "amplía", "explícame") y **no nombra su propio tema**.
    "dame más explicación" sí; "explícame qué es el pene" no, porque trae el tema consigo;
    "y el artículo 35?" tampoco: es un tema nuevo, aunque suene a continuación.
    """
    q = _LEAD_RE.sub("", query.strip())
    if not q:
        return False
    if _PRONOUN_RE.search(q):
        return True
    return bool(_FOLLOWUP_RE.match(q)) and not _has_own_subject(q)


def _plain(word: str) -> str:
    """minúsculas, sin acentos y sin signos: 'Explícame,' → 'explicame'."""
    w = unicodedata.normalize("NFD", word.lower())
    w = "".join(c for c in w if unicodedata.category(c) != "Mn")
    return w.strip("¿?¡!.,;:()\"'…-")


def _has_own_subject(query: str) -> bool:
    """¿La pregunta nombra algo por sí misma, o solo pide más de lo anterior?"""
    for raw in query.split():
        w = _plain(raw)
        if len(w) < 4 or w in _GENERIC or _META_RE.match(w):
            continue
        return True
    return False


def last_topic(history: list[dict]) -> str:
    """El último tema del que se habló: la última pregunta del usuario con sujeto propio."""
    for msg in reversed(history):
        if msg.get("role") != "user":
            continue
        content = (msg.get("content") or "").strip()
        if content and not is_followup(content):
            return content
    return ""


def rewrite_query(query: str, history: list[dict]) -> tuple[str, dict]:
    """Consulta lista para el recuperador. Devuelve (consulta, información de lo hecho).

    Sin LLM: es una reescritura barata y predecible. "dame más explicación" tras
    "¿Qué significa efímero?" se busca como "¿Qué significa efímero?", que es lo que el
    usuario quiere ampliar.
    """
    if not history or not is_followup(query):
        return query, {"rewritten": False}
    topic = last_topic(history)
    if not topic:
        return query, {"rewritten": False, "reason": "sin tema previo"}
    return topic, {"rewritten": True, "from": query, "topic": topic}


def wants_more_detail(query: str) -> bool:
    return bool(_MORE_RE.search(query))


def build_context(candidates, query: str, max_candidates: int = MAX_CANDIDATES_IN_PROMPT,
                  chars: int = CANDIDATE_CHARS) -> str:
    """Los candidatos numerados, cada uno recortado a lo que responde la pregunta."""
    lines = []
    for i, c in enumerate(candidates[:max_candidates], start=1):
        text = getattr(c, "text", str(c))
        text = focus_text(query, text, chars) if len(text) > chars else text
        key = getattr(c, "key", None) or getattr(c, "source_id", None) or ""
        head = f"[{i}]" + (f" ({key})" if key else "")
        lines.append(f"{head} {text}")
    return "\n".join(lines)


def _history_messages(history: list[dict], turns: int = HISTORY_TURNS) -> list[dict]:
    out = []
    for m in history[-turns:]:
        role = m.get("role")
        content = (m.get("content") or "").strip()
        if role in ("user", "assistant") and content:
            out.append({"role": role, "content": content[:1200]})
    return out


def messages(query: str, candidates, history: list[dict] | None = None,
             system_extra: str = "", detail: bool | None = None,
             language: str = "es") -> list[dict]:
    """Prompt de Agente B: candidatos + conversación + instrucciones de redacción."""
    history = history or []
    more = wants_more_detail(query) if detail is None else detail
    # Una pregunta con tema propio no necesita la conversación: es ruido, y un modelo
    # pequeño se engancha al último turno y lo repite en vez de responder lo nuevo.
    if not is_followup(query):
        history = []
    context = build_context(candidates, query)

    if language == "en":
        rules = [
            "You answer using ONLY the CANDIDATES that Agent A retrieved.",
            "1) Pick the candidate that answers the question and use it. Ignore the others.",
            "2) Never add facts, figures or names that are not in the candidates.",
            "3) Write for a person: full sentences, no 'candidate [2] says'.",
            ("4) The user asked for more detail: use everything relevant in the candidates. "
             "If they do not say more, answer with what they do say and add that the "
             "available sources record nothing further. Never pad with your own knowledge."
             if more else
             "4) Be brief: two or three sentences are enough."),
            "5) If no candidate answers the question, say exactly: "
            "'The available information does not cover this topic.'",
            "6) Answer THIS question. Do not repeat your previous answer if the topic changed.",
        ]
        user = f"CANDIDATES:\n{context}\n\nQUESTION: {query}"
    else:
        rules = [
            "Respondes usando ÚNICAMENTE los CANDIDATOS que recuperó el Agente A.",
            "1) Elige el candidato que responde la pregunta y úsalo. Ignora los demás.",
            "2) Nunca añadas datos, cifras ni nombres que no estén en los candidatos.",
            "3) Escribe para una persona: frases completas, sin decir 'el candidato [2]'.",
            ("4) El usuario pide más detalle: aprovecha todo lo relevante de los candidatos. "
             "Si no dicen más, responde con lo que sí dicen y avisa de que las fuentes "
             "disponibles no recogen nada más. Nunca rellenes con lo que sepas por tu cuenta."
             if more else
             "4) Sé breve: con dos o tres frases basta."),
            "5) Si ningún candidato responde la pregunta, contesta exactamente: "
            "'La información disponible no cubre este tema.'",
            "6) Responde ESTA pregunta. No repitas tu respuesta anterior si cambió el tema.",
            "7) Responde en español.",
        ]
        user = f"CANDIDATOS:\n{context}\n\nPREGUNTA: {query}"

    system = "\n".join(rules)
    if system_extra:
        system = f"{system_extra.strip()}\n\n{system}"
    return [{"role": "system", "content": system}, *_history_messages(history),
            {"role": "user", "content": user}]


def picked_candidate(answer: str, candidates) -> int | None:
    """Qué candidato usó realmente la respuesta (el de mayor solapamiento léxico)."""
    terms = content_terms(answer)
    if not terms:
        return None
    best, best_overlap = None, 0.0
    for i, c in enumerate(candidates):
        ct = content_terms(getattr(c, "text", str(c)))
        if not ct:
            continue
        overlap = len(terms & ct) / len(terms)
        if overlap > best_overlap:
            best, best_overlap = i, overlap
    return best if best_overlap >= 0.25 else None


def looks_like_refusal(answer: str) -> bool:
    a = normalize(answer)
    return "no cubre este tema" in a or "does not cover this topic" in a
