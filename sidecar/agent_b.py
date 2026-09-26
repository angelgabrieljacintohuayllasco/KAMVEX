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


AUTHORITY_MARK = "← la pregunta nombra esta"


def build_context(candidates, query: str, max_candidates: int = MAX_CANDIDATES_IN_PROMPT,
                  chars: int = CANDIDATE_CHARS) -> str:
    """Las fuentes numeradas, cada una recortada a lo que responde la pregunta.

    La fuente que la pregunta nombra entera va marcada. Sin la marca, «hazme una
    explicación muy larga de la palabra pene» hacía que Gemma 3 4B contestara la definición
    de *explicación*: la palabra estaba en la pregunta y pesaba más que el orden.
    """
    lines = []
    for i, c in enumerate(candidates[:max_candidates], start=1):
        text = getattr(c, "text", str(c))
        text = focus_text(query, text, chars) if len(text) > chars else text
        key = getattr(c, "key", None) or getattr(c, "source_id", None) or ""
        head = f"[{i}]" + (f" ({key})" if key else "")
        if getattr(c, "authority", False):
            head += f" {AUTHORITY_MARK}"
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
    marcada = any(getattr(c, "authority", False)
                  for c in candidates[:MAX_CANDIDATES_IN_PROMPT])

    if language == "en":
        rules = [
            ("Below are numbered sources. One is marked: the question names it, so that is "
             "the one to answer from." if marcada else
             "Below are numbered sources. Find the one that answers the question and answer "
             "with what it says."),
            "Never add facts, figures or names that are not in the sources.",
            "Only if no source answers the question at all, reply with this single sentence "
            "and nothing else: 'The available information does not cover this topic.'",
            (("The user asked for more detail: use everything that marked source says, and "
              "nothing from the others. If it says no more, answer with what it does say and "
              "add one line saying so." if marcada else
              "The user asked for more detail: use everything relevant from the source that "
              "answers. If it says no more, answer with what it does say and add one line "
              "saying so.") if more else "Be brief: two or three sentences."),
            "Write one continuous text. Never paste sources one after another, and never "
            "repeat the same one twice.",
            "Answer THIS question, not the previous one.",
            "Write only the answer: no preamble, no headings, no numbering, do not quote "
            "these instructions and do not mention sources, options or candidates.",
        ]
        user = f"SOURCES:\n{context}\n\nQUESTION: {query}"
    else:
        rules = [
            ("Abajo tienes fuentes numeradas. Una está marcada: la pregunta la nombra, así "
             "que es esa la que debes usar para responder." if marcada else
             "Abajo tienes fuentes numeradas. Busca la que responde la pregunta y contesta "
             "con lo que dice."),
            "Nunca añadas datos, cifras ni nombres que no estén en las fuentes.",
            "Solo si ninguna fuente responde la pregunta, contesta con esta frase y nada "
            "más: 'La información disponible no cubre este tema.'",
            (("El usuario pide más detalle: aprovecha todo lo que diga esa fuente marcada, y "
              "nada de las demás. Si no dice más, respóndelo y añade una línea diciéndolo."
              if marcada else
              "El usuario pide más detalle: aprovecha todo lo relevante de la fuente que "
              "responde. Si no dice más, respóndelo y añade una línea diciéndolo.")
             if more else "Sé breve: dos o tres frases."),
            "Escribe un texto seguido. Nunca pegues fuentes una detrás de otra ni repitas "
            "la misma dos veces.",
            "Responde ESTA pregunta, no la anterior.",
            "Responde en español y escribe solo la respuesta: sin preámbulo, sin "
            "encabezados, sin numerar, sin repetir estas instrucciones y sin mencionar "
            "fuentes, opciones ni candidatos.",
        ]
        user = f"FUENTES:\n{context}\n\nPREGUNTA: {query}"

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


_REFUSALS = ("no cubre este tema", "does not cover this topic")
# Una negativa pegada al final de una respuesta larga no es una negativa: es una coletilla
# que el modelo añade por obedecer la regla al pie de la letra. Medido con Gemma 3 4B, esa
# coletilla saltaba el guardarraíl entero y la respuesta salía sin comprobar.
REFUSAL_SLACK = 40


def _fold(text: str) -> tuple[str, list[int]]:
    """Texto en minúsculas y sin acentos, con la posición original de cada carácter.

    `normalize` descompone y borra tildes, así que acorta la cadena: sus posiciones no
    sirven para recortar el original. Aquí se guarda el mapa.
    """
    out, idx = [], []
    for i, ch in enumerate(text):
        for c in unicodedata.normalize("NFD", ch.lower()):
            if unicodedata.category(c) != "Mn":
                out.append(c)
                idx.append(i)
    return "".join(out), idx


def _refusal_span(answer: str) -> tuple[int, int] | None:
    """Dónde empieza y acaba la frase de negativa en el texto ORIGINAL, si está."""
    folded, idx = _fold(answer)
    for phrase in _REFUSALS:
        i = folded.find(phrase)
        if i >= 0:
            fin = i + len(phrase) - 1
            return idx[i], idx[fin] + 1
    return None


def looks_like_refusal(answer: str) -> bool:
    """¿La respuesta **es** la negativa, o solo la lleva pegada al final?"""
    span = _refusal_span(answer)
    if span is None:
        return False
    resto = len(answer.strip()) - (span[1] - span[0])
    return resto <= REFUSAL_SLACK


def strip_refusal_tail(answer: str) -> str:
    """Quita la negativa cuando el modelo ya había respondido antes de añadirla.

    Se borra la **oración entera**, no solo la frase clave: cortar en «no cubre este
    tema» dejaba colgando «La información disponible».
    """
    span = _refusal_span(answer)
    if span is None or looks_like_refusal(answer):
        return answer
    ini, fin = span
    while ini > 0 and answer[ini - 1] not in ".!?\n":
        ini -= 1
    while fin < len(answer) and answer[fin] not in ".!?\n":
        fin += 1
    if fin < len(answer):
        fin += 1
    resto = (answer[:ini].rstrip() + " " + answer[fin:].strip()).strip()
    return resto or answer


# Marcadores del prompt que un modelo pequeño copia al empezar.
_MARKER_RE = re.compile(
    r"^\s*(?:FUENTES|SOURCES|CANDIDATOS|CANDIDATES|PREGUNTA|QUESTION)\s*:?\s*$",
    re.IGNORECASE)
# El marcador «[2] (clave)» con el que se numeran las fuentes en el prompt.
_LABEL_RE = re.compile(r"^\[\d+\]\s*(?:\([^)]*\))?\s*")
# Arranque del tipo «ÚNICAMENTE EL CANDIDATO [1] dice lo siguiente sobre X:».
_PREFACE_RE = re.compile(
    r"^\s*[^.\n]{0,120}?\b(?:candidat\w*|fuente\w*|opci[oó]n\w*|source\w*|option\w*)\b"
    r"[^.\n]{0,120}?:\s*", re.IGNORECASE)


def strip_prompt_echo(answer: str, instructions: str = "") -> str:
    """Quita el preámbulo cuando el modelo repite las instrucciones o los marcadores.

    Medido: Gemma 3 4B devolvió «Elige el candidato que responde la pregunta y úsalo.
    Ignora los demás.» seguido del bloque de fuentes, y Qwen2.5 3B empezó con «ÚNICAMENTE
    EL CANDIDATO [1] Dice lo siguiente sobre el Artículo 2:».

    Se comparan las líneas iniciales con las **instrucciones**, no con las fuentes: citar
    la fuente al pie de la letra es justo lo que debe hacer una respuesta anclada, y
    borrarla por parecerse al prompt dejaría sin respuesta al usuario.
    """
    fondo = _fold(instructions)[0] if instructions else ""
    util: list[str] = []
    saltando = True
    for linea in answer.strip().splitlines():
        limpia = linea.strip()
        if saltando:
            if not limpia:
                continue
            # Un «[2] » al principio es el marcador del bloque de fuentes; lo que venga
            # detrás puede ser del modelo, así que se quita el marcador, no la línea.
            limpia = _LABEL_RE.sub("", limpia, count=1).strip()
            if not limpia:
                continue
            plegada = _fold(limpia)[0]
            if _MARKER_RE.match(limpia) or (fondo and len(plegada) > 12 and plegada in fondo):
                continue
            saltando = False
            linea = limpia
        util.append(linea)
    out = "\n".join(util).strip()
    return _PREFACE_RE.sub("", out, count=1).strip()
