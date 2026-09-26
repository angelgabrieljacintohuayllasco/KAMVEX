"""
Errores con nombre, código correcto y una frase que dice qué hacer.

El usuario vio «TypeError: Failed to fetch» en rojo al preguntar. No era la red: el sidecar
devolvía un 500 desde `ServerErrorMiddleware`, que en Starlette es **la capa más externa**,
por fuera de `CORSMiddleware` (https://www.starlette.io/middleware/). Sin cabeceras CORS el
navegador descarta la respuesta y `fetch` falla como si el servidor no existiera. El usuario
no ve «el prompt no cabe en el contexto»: ve que la aplicación está rota.

Aquí hay dos cosas:

1. `classify()` traduce cualquier excepción a un código HTTP y una frase accionable. Un
   error que no dice qué hacer es un error a medias.
2. `ErrorMiddleware` es la red de seguridad: se registra **antes** que CORS —y por tanto
   queda por dentro, porque `add_middleware` inserta al principio— para que su respuesta
   salga con las cabeceras puestas. Es ASGI puro y no toca el cuerpo, así que las descargas
   por SSE siguen fluyendo sin quedarse en memoria.
"""

from __future__ import annotations

import json
import logging
import re

from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

log = logging.getLogger("kamvex.errors")

# ── Mensajes ────────────────────────────────────────────────────────────────
# Cada uno dice qué pasó y qué hacer. Sin jerga y sin culpar al usuario.

SIN_MOTOR = ("No hay ningún modelo cargado. Elige uno en el selector de arriba y espera a "
             "que termine de arrancar.")
CARGANDO = ("El modelo todavía se está cargando en memoria. Espera unos segundos y vuelve "
            "a enviar la pregunta.")
MOTOR_CAIDO = ("El motor de inferencia no responde. Vuelve a seleccionar el modelo para "
               "reiniciarlo.")
SIN_ESPACIO = ("No queda espacio en disco para completar la operación. Libera espacio y "
               "vuelve a intentarlo.")
SIN_RED = ("No se pudo conectar con el servidor de descargas. Revisa tu conexión y vuelve "
           "a intentarlo.")
RESPUESTA_RARA = ("El servidor de inferencia devolvió algo que no se entiende. Vuelve a "
                  "seleccionar el modelo para reiniciarlo.")
INESPERADO = ("Algo falló dentro de KAMVEX y la operación no se completó. Vuelve a "
              "intentarlo; si se repite, mira el registro en Ajustes.")

# El texto exacto que devuelve llama-server cuando el prompt no cabe.
_OVERFLOW_RE = re.compile(
    r"request \((\d+) tokens\) exceeds the available context size \((\d+) tokens\)",
    re.IGNORECASE)


def context_overflow(message: str) -> dict | None:
    """Cuántos tokens se pidieron y cuántos caben, si el error es de contexto lleno."""
    if not message:
        return None
    m = _OVERFLOW_RE.search(str(message))
    if m:
        return {"pedidos": int(m.group(1)), "disponibles": int(m.group(2))}
    # Algunas compilaciones lo mandan como JSON con el tipo, sin la frase completa.
    if "exceed_context_size" in str(message):
        try:
            i = str(message).index("{")
            data = json.loads(str(message)[i:]).get("error", {})
            return {"pedidos": int(data.get("n_prompt_tokens", 0)),
                    "disponibles": int(data.get("n_ctx", 0))}
        except (ValueError, TypeError, KeyError):
            return {"pedidos": 0, "disponibles": 0}
    return None


def overflow_message(info: dict) -> str:
    """La frase para el usuario cuando el prompt no cabe."""
    cabe = info.get("disponibles") or 0
    pide = info.get("pedidos") or 0
    detalle = f" (hacen falta {pide} y el contexto es de {cabe})" if cabe else ""
    return (f"La pregunta y sus fuentes no caben en el contexto del modelo{detalle}. "
            "Prueba con una pregunta más corta, empieza un chat nuevo, o elige un modelo "
            "con más contexto en Modelos.")


def classify(exc: BaseException) -> tuple[int, str]:
    """De una excepción cualquiera al par (código HTTP, frase accionable).

    No se filtra el texto interno al usuario: va al registro. Lo que llega a la pantalla
    dice qué pasó y qué hacer.
    """
    texto = str(exc)

    info = context_overflow(texto)
    if info is not None:
        return 413, overflow_message(info)

    if isinstance(exc, MemoryError):
        return 507, ("No hay memoria suficiente para este modelo. Cierra otras aplicaciones "
                     "o elige un modelo más pequeño.")
    if isinstance(exc, json.JSONDecodeError):
        return 502, RESPUESTA_RARA

    bajo = texto.lower()
    if "no disponible" in bajo or "connection refused" in bajo or "actively refused" in bajo:
        return 503, MOTOR_CAIDO
    if "sigue cargando" in bajo or "loading model" in bajo or "503" in bajo:
        return 503, CARGANDO
    if isinstance(exc, OSError):
        if getattr(exc, "errno", None) == 28 or "no space" in bajo or "espacio" in bajo:
            return 507, SIN_ESPACIO
        if "getaddrinfo" in bajo or "timed out" in bajo or "urlopen" in bajo:
            return 502, SIN_RED
        return 500, INESPERADO
    return 500, INESPERADO


def validation_detail(exc: RequestValidationError) -> str:
    """El 422 de Pydantic, en una frase. La lista cruda no la entiende nadie."""
    partes = []
    for err in exc.errors()[:4]:
        campo = ".".join(str(x) for x in err.get("loc", []) if x != "body") or "el cuerpo"
        partes.append(f"{campo}: {err.get('msg', 'valor inválido')}")
    return "La petición no es válida — " + "; ".join(partes) if partes else "Petición inválida."


class ErrorMiddleware:
    """Red de seguridad: ninguna excepción llega al navegador sin traducir.

    ASGI puro a propósito. `BaseHTTPMiddleware` almacena el cuerpo y rompería las
    descargas por SSE de `/datasets/install`, que es justo lo que no se puede romper.
    """

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope.get("type") != "http":
            return await self.app(scope, receive, send)

        empezada = False

        async def enviar(message):
            nonlocal empezada
            if message["type"] == "http.response.start":
                empezada = True
            await send(message)

        try:
            await self.app(scope, receive, enviar)
        except Exception as exc:  # noqa: BLE001 — esa es la función de esta clase
            if empezada:
                # La cabecera ya salió: no se puede reescribir la respuesta a medias.
                log.exception("fallo con la respuesta ya empezada en %s", scope.get("path"))
                raise
            codigo, mensaje = classify(exc)
            log.exception("%s %s -> %s", scope.get("method"), scope.get("path"), codigo)
            respuesta = JSONResponse({"detail": mensaje}, status_code=codigo)
            await respuesta(scope, receive, send)


def install(app, cors_kwargs: dict) -> None:
    """Monta la red de seguridad y CORS, en el orden que importa.

    `add_middleware` inserta al principio de la lista y la lista se aplica de fuera adentro,
    así que **el último en registrarse queda más externo**. CORS va el último para poder
    poner sus cabeceras también en las respuestas de error.
    """
    from fastapi.middleware.cors import CORSMiddleware
    from starlette.exceptions import HTTPException as StarletteHTTPException

    app.add_middleware(ErrorMiddleware)
    app.add_middleware(CORSMiddleware, **cors_kwargs)

    @app.exception_handler(RequestValidationError)
    async def _validacion(request, exc):  # noqa: ANN001
        return JSONResponse({"detail": validation_detail(exc)}, status_code=422)

    @app.exception_handler(StarletteHTTPException)
    async def _http(request, exc):  # noqa: ANN001
        detalle = exc.detail if isinstance(exc.detail, str) else str(exc.detail)
        if exc.status_code == 404 and not detalle.strip():
            detalle = "Esa ruta no existe en el sidecar."
        return JSONResponse({"detail": detalle}, status_code=exc.status_code,
                            headers=getattr(exc, "headers", None))
