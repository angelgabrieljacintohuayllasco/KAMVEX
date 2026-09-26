"""Ninguna ruta puede devolver un 500 mudo.

El usuario vio «TypeError: Failed to fetch» en rojo. No era un fallo de red: el sidecar
devolvía un 500 desde `ServerErrorMiddleware`, que en Starlette es la capa **más externa**
y por tanto queda por fuera de `CORSMiddleware`. Sin cabeceras CORS el navegador descarta
la respuesta y `fetch` falla como si el servidor no existiera.

Regla: toda respuesta de error lleva JSON, cabeceras CORS y una frase que diga qué hacer.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

import server
from conftest import FakeConnector

ORIGIN = "http://localhost:1420"


@pytest.fixture
def cliente():
    """Cliente que manda Origin, como hace la app, y no se traga las excepciones."""
    with TestClient(server.app, raise_server_exceptions=False) as c:
        yield c


def _headers():
    return {"Origin": ORIGIN}


# ── C1: nada sale sin CORS ni sin explicación ──────────────────────────────

def test_una_excepcion_imprevista_sale_como_json_con_cors(cliente, monkeypatch):
    """Si algo revienta donde nadie lo esperaba, el navegador tiene que poder leerlo."""
    class DiscoRoto:
        def exists(self):
            raise RuntimeError("algo raro de verdad")

    monkeypatch.setattr(server, "DATA_DIR", DiscoRoto())
    r = cliente.get("/datasets", headers=_headers())
    assert r.status_code == 500
    assert r.headers.get("access-control-allow-origin") == ORIGIN, "sin CORS = Failed to fetch"
    cuerpo = r.json()
    assert cuerpo["detail"], "un error sin mensaje no ayuda a nadie"
    assert "algo raro de verdad" not in cuerpo["detail"], "no se filtran detalles internos"


def test_un_error_http_normal_tambien_lleva_cors(cliente):
    r = cliente.post("/chat", json={"dataset": "no-existe", "query": "hola"}, headers=_headers())
    assert r.status_code >= 400
    assert r.headers.get("access-control-allow-origin") == ORIGIN
    assert r.json()["detail"]


def test_un_cuerpo_invalido_explica_que_falta(cliente):
    r = cliente.post("/chat", json={"query": 123}, headers=_headers())
    assert r.status_code == 422
    assert r.headers.get("access-control-allow-origin") == ORIGIN
    assert isinstance(r.json()["detail"], str), "el 422 de Pydantic debe venir legible"


def test_una_ruta_que_no_existe_no_rompe_el_navegador(cliente):
    r = cliente.get("/no-existe", headers=_headers())
    assert r.status_code == 404
    assert r.headers.get("access-control-allow-origin") == ORIGIN


# ── C2: el contexto lleno es un aviso, no una caída ────────────────────────

class _ContextFull(FakeConnector):
    """llama-server cuando el prompt no cabe. Mensaje textual del servidor real."""

    def __call__(self, messages):
        self.calls.append(messages)
        raise RuntimeError(
            'llama-server respondió HTTP 400: {"error":{"code":400,"message":"request '
            '(3692 tokens) exceeds the available context size (2048 tokens), try increasing '
            'it","type":"exceed_context_size_error","n_prompt_tokens":3692,"n_ctx":2048}}')


@pytest.mark.skipif(not server._DASA_AVAILABLE, reason="DASA/SHARD not importable")
def test_el_contexto_lleno_se_explica_no_revienta(sidecar, monkeypatch):
    """Era el error exacto de la captura del usuario."""
    from conftest import build_dataset
    build_dataset(sidecar, "demo")
    monkeypatch.setattr(server, "_LLAMA_CONNECTOR", _ContextFull())
    r = sidecar.post("/chat", json={"dataset": "demo", "query": "explicame mis derechos",
                                    "agent_b_mode": "free"})
    assert r.status_code == 413, "el contexto lleno es un 413, no un 500"
    detalle = r.json()["detail"]
    assert "contexto" in detalle.lower()
    assert "2048" in detalle, "hay que decir cuánto cabe"


def test_el_mensaje_del_contexto_lleno_se_reconoce():
    from errors import context_overflow
    crudo = ('llama-server respondió HTTP 400: {"error":{"code":400,"message":"request '
             '(3692 tokens) exceeds the available context size (2048 tokens), try increasing '
             'it","type":"exceed_context_size_error","n_prompt_tokens":3692,"n_ctx":2048}}')
    info = context_overflow(crudo)
    assert info == {"pedidos": 3692, "disponibles": 2048}


def test_otros_errores_no_se_confunden_con_contexto_lleno():
    from errors import context_overflow
    assert context_overflow("llama-server no disponible: connection refused") is None
    assert context_overflow("") is None


# ── El motor apagado se dice, no se calla ──────────────────────────────────

@pytest.mark.skipif(not server._DASA_AVAILABLE, reason="DASA/SHARD not importable")
def test_sin_motor_el_mensaje_dice_que_hacer(sidecar, monkeypatch):
    from conftest import build_dataset
    build_dataset(sidecar, "demo")
    monkeypatch.setattr(server, "_LLAMA_CONNECTOR", None)
    r = sidecar.post("/chat", json={"dataset": "demo", "query": "hola", "agent_b_mode": "free"})
    assert r.status_code == 503
    detalle = r.json()["detail"].lower()
    assert "modelo" in detalle or "motor" in detalle


# ── Barrido: ninguna ruta se comporta mal ──────────────────────────────────

def _rutas():
    """Todas las rutas declaradas, con su método, menos las de documentación."""
    fuera = {"/openapi.json", "/docs", "/docs/oauth2-redirect", "/redoc"}
    for r in server.app.routes:
        path = getattr(r, "path", "")
        if path in fuera or not getattr(r, "methods", None):
            continue
        for metodo in sorted(r.methods - {"HEAD", "OPTIONS"}):
            yield metodo, path


def test_hay_rutas_que_barrer():
    assert len(list(_rutas())) > 20


def test_ninguna_ruta_devuelve_un_error_mudo(cliente):
    """Con parámetros basura, toda ruta responde algo que el navegador entiende."""
    malos = {"name": "no-existe", "dataset": "no-existe", "expert": "no-existe",
             "job_id": "no-existe", "download_id": "no-existe", "model": "no-existe",
             "id": "no-existe", "expert_id": "no-existe", "filename": "no-existe"}
    revisadas = 0
    for metodo, plantilla in _rutas():
        path = plantilla
        for clave, valor in malos.items():
            path = path.replace("{" + clave + "}", valor)
        if "{" in path:
            continue                      # parámetro que no sabemos inventar
        r = cliente.request(metodo, path, json={}, headers=_headers())
        revisadas += 1
        assert r.headers.get("access-control-allow-origin") == ORIGIN, f"{metodo} {path} sin CORS"
        if r.status_code >= 400:
            cuerpo = r.json()
            assert isinstance(cuerpo, dict) and cuerpo.get("detail"), f"{metodo} {path} sin detalle"
            assert isinstance(cuerpo["detail"], str), f"{metodo} {path}: detalle ilegible"
            assert "Traceback" not in cuerpo["detail"], f"{metodo} {path} filtra el traceback"
    assert revisadas >= 15, f"solo se barrieron {revisadas} rutas"


def test_ningun_mensaje_de_error_esta_vacio_o_es_un_objeto(cliente):
    for metodo, plantilla in _rutas():
        if "{" in plantilla:
            continue
        r = cliente.request(metodo, plantilla, json={"query": None}, headers=_headers())
        if r.status_code < 400:
            continue
        detalle = r.json().get("detail", "")
        assert detalle and detalle != "[object Object]", f"{metodo} {plantilla}: «{detalle}»"
        assert len(detalle) > 10, f"{metodo} {plantilla}: mensaje demasiado corto «{detalle}»"


# ── El streaming no se puede romper: las descargas van por SSE ─────────────

def _recorrer(app) -> bytes:
    """Ejecuta una app ASGI y junta los trozos del cuerpo.

    El `receive` devuelve `http.disconnect` a partir de la segunda llamada: sin eso,
    `StreamingResponse` se queda esperando a que el cliente se vaya y el test no termina.
    """
    import asyncio

    partes: list[bytes] = []
    llamadas = {"n": 0}

    async def receive():
        llamadas["n"] += 1
        if llamadas["n"] == 1:
            return {"type": "http.request", "body": b"", "more_body": False}
        return {"type": "http.disconnect"}

    async def send(message):
        if message["type"] == "http.response.body":
            partes.append(message.get("body", b""))

    async def correr():
        await asyncio.wait_for(
            app({"type": "http", "method": "GET", "path": "/x", "headers": []}, receive, send),
            timeout=10)

    asyncio.run(correr())
    return b"".join(partes)


def _app_que_devuelve(response):
    async def app(scope, receive, send):
        await response(scope, receive, send)
    return app


def test_el_middleware_no_rompe_el_streaming():
    """`BaseHTTPMiddleware` almacenaría el cuerpo entero; por eso el nuestro es ASGI puro.

    Si se bufferizara, la barra de una descarga de 5 GB no se movería hasta el final.
    """
    from starlette.responses import StreamingResponse

    async def trozos():
        for i in range(5):
            yield f"data: {i}\n\n".encode()

    app = server.errors_mod.ErrorMiddleware(
        _app_que_devuelve(StreamingResponse(trozos(), media_type="text/event-stream")))
    assert _recorrer(app).count(b"data: ") == 5, "el middleware se comió los trozos"


def test_un_fallo_antes_de_la_cabecera_si_se_traduce():
    async def revienta(scope, receive, send):
        raise RuntimeError("antes de responder")

    app = server.errors_mod.ErrorMiddleware(revienta)
    cuerpo = _recorrer(app)
    assert b"detail" in cuerpo
    assert b"antes de responder" not in cuerpo, "no se filtra el detalle interno"
