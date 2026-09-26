"""El prompt tiene que caber. Siempre.

Aunque el contexto sea generoso, una conversación larga con varias fuentes acaba
desbordándolo. Que el usuario reciba «request (3692 tokens) exceeds the available context
size (2048 tokens)» no es aceptable: el sidecar sabe cuánto cabe y tiene que recortar antes
de enviar, empezando por lo que menos duele.
"""

from __future__ import annotations

import json

import context as ctx_mod
from agent_b import messages


class C:
    def __init__(self, key, text):
        self.key, self.text, self.source_id = key, text, key


LARGO = C("Artículo 2", "Artículo 2: Toda persona tiene derecho. " * 120)
CORTO = C("Artículo 55", "Artículo 55: Los tratados forman parte del derecho nacional.")


# ── Estimar tokens ─────────────────────────────────────────────────────────

def test_estimar_tokens_crece_con_el_texto():
    assert ctx_mod.estimate_tokens("") == 0
    corto = ctx_mod.estimate_tokens("hola")
    largo = ctx_mod.estimate_tokens("hola " * 500)
    assert 0 < corto < largo


def test_la_estimacion_no_se_queda_corta():
    """Pasarse por arriba cuesta contexto; quedarse corto cuesta una respuesta rota."""
    texto = "Artículo 2: Toda persona tiene derecho a la vida. " * 40
    # Una regla prudente para el español: nunca menos de un token cada 4 caracteres.
    assert ctx_mod.estimate_tokens(texto) >= len(texto) / 4


def test_contar_los_mensajes_incluye_la_sobrecarga_de_cada_turno():
    uno = [{"role": "user", "content": "hola"}]
    tres = [{"role": "user", "content": "hola"}] * 3
    assert ctx_mod.messages_tokens(tres) > ctx_mod.messages_tokens(uno) * 2


# ── Leer el contexto vivo del servidor ─────────────────────────────────────

def test_lee_el_contexto_del_servidor(monkeypatch):
    class FakeResp:
        def read(self):
            return json.dumps({"default_generation_settings": {"n_ctx": 8192}}).encode()

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    monkeypatch.setattr(ctx_mod.urllib.request, "urlopen", lambda *a, **k: FakeResp())
    assert ctx_mod.probe_ctx("http://127.0.0.1:8080") == 8192


def test_lee_el_contexto_en_la_raiz(monkeypatch):
    """Algunas compilaciones lo ponen directamente en /props."""
    class FakeResp:
        def read(self):
            return json.dumps({"n_ctx": 4096}).encode()

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    monkeypatch.setattr(ctx_mod.urllib.request, "urlopen", lambda *a, **k: FakeResp())
    assert ctx_mod.probe_ctx("http://127.0.0.1:8080") == 4096


def test_si_el_servidor_no_contesta_no_revienta(monkeypatch):
    def boom(*a, **k):
        raise OSError("connection refused")

    monkeypatch.setattr(ctx_mod.urllib.request, "urlopen", boom)
    assert ctx_mod.probe_ctx("http://127.0.0.1:8080") is None


# ── Presupuesto ────────────────────────────────────────────────────────────

def test_el_presupuesto_reserva_sitio_para_la_respuesta():
    assert ctx_mod.prompt_budget(4096, 512) == 4096 - 512 - ctx_mod.SAFETY_MARGIN


def test_un_contexto_minusculo_deja_algo_de_sitio():
    assert ctx_mod.prompt_budget(512, 400) >= ctx_mod.MIN_PROMPT_TOKENS


# ── El prompt se recorta hasta que cabe ────────────────────────────────────

def test_el_prompt_se_recorta_para_caber():
    cands = [LARGO, LARGO, LARGO, LARGO]
    sin_tope = messages("¿Qué dice el Artículo 2?", cands)
    grande = ctx_mod.messages_tokens(sin_tope)
    con_tope = messages("¿Qué dice el Artículo 2?", cands, budget=grande // 3)
    assert ctx_mod.messages_tokens(con_tope) <= grande // 3
    assert ctx_mod.messages_tokens(con_tope) < grande


def test_recortar_no_borra_la_pregunta_ni_las_reglas():
    cands = [LARGO] * 6
    msgs = messages("¿Qué dice el Artículo 2?", cands, budget=300)
    assert msgs[0]["role"] == "system" and msgs[0]["content"]
    assert msgs[-1]["role"] == "user"
    assert "¿Qué dice el Artículo 2?" in msgs[-1]["content"]


def test_se_sacrifica_primero_la_conversacion():
    """Las fuentes responden la pregunta; los turnos viejos solo dan contexto."""
    hist = [{"role": "user", "content": "algo viejo " * 60},
            {"role": "assistant", "content": "respuesta vieja " * 60}]
    holgado = messages("dame más", [CORTO], history=hist)
    apretado = messages("dame más", [CORTO], history=hist,
                        budget=ctx_mod.messages_tokens(holgado) - 40)
    assert len(apretado) < len(holgado), "debería haber soltado turnos"
    assert CORTO.text[:30] in apretado[-1]["content"], "la fuente se queda"


def test_sin_presupuesto_no_se_toca_nada():
    cands = [LARGO, CORTO]
    assert messages("x", cands) == messages("x", cands, budget=None)


def test_un_presupuesto_imposible_deja_lo_minimo():
    msgs = messages("¿Qué dice el Artículo 2?", [LARGO] * 4, budget=1)
    assert len(msgs) == 2
    assert "¿Qué dice el Artículo 2?" in msgs[-1]["content"]


# ── El ajuste en el servidor: la ruta que reventó en manos del usuario ─────

import server  # noqa: E402


class _Frag:
    def __init__(self, text, source_id="k", score=1.0):
        self.text, self.source_id, self.score = text, source_id, score


def test_fit_chat_suelta_los_turnos_viejos_primero():
    msgs = [{"role": "system", "content": "reglas"}]
    msgs += [{"role": "user", "content": f"turno viejo {i} " * 50} for i in range(8)]
    msgs += [{"role": "user", "content": "la pregunta de ahora"}]
    cabe = server._fit_chat(msgs, 300)
    assert ctx_mod.messages_tokens(cabe) <= 300
    assert cabe[0]["content"] == "reglas"
    assert cabe[-1]["content"] == "la pregunta de ahora"


def test_fit_chat_no_toca_lo_que_ya_cabe():
    msgs = [{"role": "system", "content": "reglas"}, {"role": "user", "content": "hola"}]
    assert server._fit_chat(msgs, 10_000) == msgs


def test_fit_chat_con_un_presupuesto_imposible_recorta_la_pregunta():
    msgs = [{"role": "system", "content": "reglas"},
            {"role": "user", "content": "pregunta larguísima " * 300}]
    cabe = server._fit_chat(msgs, 200)
    assert len(cabe) == 2
    assert len(cabe[-1]["content"]) < len(msgs[-1]["content"])


def test_fit_fragments_entrega_menos_material_cuando_no_cabe():
    """Modo Libre: el prompt lo arma DASA, así que se controla lo que recibe."""
    largos = [_Frag("Artículo 2: Toda persona tiene derecho. " * 200, f"a{i}") for i in range(5)]
    sin_tope = sum(ctx_mod.estimate_tokens(f.text) for f in largos)
    ajustados = server._fit_fragments(largos, "explicame mis derechos", 400)
    cabe = sum(ctx_mod.estimate_tokens(f.text) for f in ajustados)
    assert cabe < sin_tope
    assert cabe <= 400
    assert ajustados, "siempre queda algo que responder"


def test_fit_fragments_no_recorta_si_ya_cabe():
    cortos = [_Frag("Artículo 55: Los tratados forman parte del derecho nacional.")]
    assert server._fit_fragments(cortos, "tratados", 10_000) == cortos


def test_fit_fragments_sin_nada_devuelve_nada():
    assert server._fit_fragments([], "x", 500) == []


def test_el_presupuesto_usa_el_contexto_vivo_del_servidor(monkeypatch):
    class Conn:
        base_url = "http://127.0.0.1:9999"

    monkeypatch.setattr(ctx_mod, "probe_ctx", lambda *a, **k: 8192)
    server._CTX_CACHE.clear()
    assert server._prompt_budget(Conn(), 512) == ctx_mod.prompt_budget(8192, 512)


def test_si_no_se_puede_preguntar_se_usa_el_valor_prudente(monkeypatch):
    class Conn:
        base_url = "http://127.0.0.1:9998"

    monkeypatch.setattr(ctx_mod, "probe_ctx", lambda *a, **k: None)
    server._CTX_CACHE.clear()
    assert server._prompt_budget(Conn(), 512) == ctx_mod.prompt_budget(ctx_mod.DEFAULT_CTX, 512)


def test_el_reintento_aprende_el_contexto_real(monkeypatch):
    """El 400 del servidor trae el n_ctx bueno: el segundo intento ya va con ese número."""
    intentos = []

    class Conn:
        base_url = "http://127.0.0.1:9997"

        def __call__(self, msgs):
            intentos.append(msgs)
            if len(intentos) == 1:
                raise RuntimeError(
                    'llama-server respondió HTTP 400: {"error":{"code":400,"message":"request '
                    '(3692 tokens) exceeds the available context size (2048 tokens)"}}')
            return "respuesta corta"

    server._CTX_CACHE.clear()
    visto = {}

    def rebuild(limite):
        visto["limite"] = limite
        return [{"role": "user", "content": "menos"}]

    assert server._ask(Conn(), [{"role": "user", "content": "mucho"}], rebuild) == "respuesta corta"
    assert len(intentos) == 2
    assert visto["limite"] < 2048, "el segundo intento tiene que pedir menos"
    assert server._CTX_CACHE["http://127.0.0.1:9997"] == 2048


def test_si_ni_el_reintento_cabe_se_devuelve_413(monkeypatch):
    from fastapi import HTTPException
    import pytest as _pytest

    class Conn:
        base_url = "http://127.0.0.1:9996"

        def __call__(self, msgs):
            raise RuntimeError(
                'llama-server respondió HTTP 400: {"error":{"code":400,"message":"request '
                '(900 tokens) exceeds the available context size (512 tokens)"}}')

    server._CTX_CACHE.clear()
    with _pytest.raises(HTTPException) as exc:
        server._ask(Conn(), [{"role": "user", "content": "x"}], lambda n: [{"role": "user", "content": "y"}])
    assert exc.value.status_code == 413
    assert "contexto" in exc.value.detail.lower()
