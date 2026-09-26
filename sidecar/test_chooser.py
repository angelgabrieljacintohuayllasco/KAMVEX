"""Los modelos de decisión eligen qué candidato responde, sin generar texto.

Contrato común de Laya, Kev, Von, SemIf y NanoJev: estado + opciones → una probabilidad
por opción. `LogitChooser` lo implementa con el llama-server que ya corre.
"""

import json
import math
import urllib.error

import chooser
from chooser import (
    Decision,
    ExternalChooser,
    LogitChooser,
    choosers_from_env,
    decide,
    options_prompt,
    reorder,
)


class C:
    def __init__(self, key, text):
        self.key, self.text, self.source_id = key, text, key


ART2 = C("Artículo 2", "Artículo 2: Toda persona tiene derecho a la vida, a su identidad y a "
                       "su integridad moral, psíquica y física.")
ART35 = C("Artículo 35", "Artículo 35: Los ciudadanos pueden ejercer sus derechos a través de "
                         "organizaciones políticas.")
ART55 = C("Artículo 55", "Artículo 55: Los tratados celebrados por el Estado forman parte del "
                         "derecho nacional.")
CANDS = [ART55, ART2, ART35]          # el bueno va segundo: el Agente A no siempre acierta


def _chat_response(labels: dict[str, float]):
    """Lo que devuelve /v1/chat/completions con logprobs: la ruta principal."""
    return {"choices": [{"message": {"content": "2"}, "logprobs": {"content": [
        {"token": "2", "top_logprobs": [{"token": t, "logprob": lp} for t, lp in labels.items()]}
    ]}}]}


def _logprob_response(labels: dict[str, float]):
    """Lo que devuelve /completion con n_probs: la ruta de respaldo."""
    return {"completion_probabilities": [
        {"token": "", "top_logprobs": [{"token": t, "logprob": lp} for t, lp in labels.items()]}
    ]}


def _fake_http(monkeypatch, payload):
    class FakeResp:
        def read(self):
            return json.dumps(payload).encode("utf-8")

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    monkeypatch.setattr(chooser.urllib.request, "urlopen", lambda req, timeout=None: FakeResp())


# ── El prompt de opciones ───────────────────────────────────────────────────

def test_el_prompt_numera_las_opciones_y_termina_donde_va_la_etiqueta():
    p = options_prompt("¿Qué dice el Artículo 2?", CANDS)
    assert "PREGUNTA: ¿Qué dice el Artículo 2?" in p
    assert "1. Artículo 55:" in p and "2. Artículo 2:" in p and "3. Artículo 35:" in p
    assert p.rstrip().endswith("Responde solo con el número de la opción correcta.")


def test_el_prompt_recorta_las_opciones_largas():
    largo = C("x", "relleno. " * 400 + "El dato clave es la uretra.")
    p = options_prompt("uretra", [largo, ART2], chars=200)
    assert len(p) < 1200
    assert "uretra" in p


def test_el_prompt_no_pasa_de_ocho_opciones():
    muchos = [C(f"k{i}", f"texto {i}") for i in range(20)]
    p = options_prompt("x", muchos)
    assert "8. texto 7" in p and "9. texto 8" not in p


# ── LogitChooser: la técnica de SemIf ───────────────────────────────────────

def test_lee_las_probabilidades_de_las_etiquetas(monkeypatch):
    """El modelo prefiere la etiqueta 2, que es el Artículo 2: el bueno."""
    _fake_http(monkeypatch, _chat_response({"2": -0.2, "1": -2.5, "3": -3.0, "**": -1.0}))
    scores = LogitChooser("http://127.0.0.1:8080").choose("¿Qué dice el Artículo 2?", CANDS)
    assert len(scores) == 3
    assert abs(sum(scores) - 1.0) < 1e-6
    assert scores[1] == max(scores)
    assert scores[1] > 0.6


def test_ignora_los_tokens_que_no_son_etiquetas(monkeypatch):
    """«**», « ]» y demás ruido del modelo no son opciones."""
    _fake_http(monkeypatch, _chat_response({"**": -0.1, " ]": -0.2, "2": -1.0, "1": -3.0}))
    scores = LogitChooser("http://127.0.0.1:8080").choose("x", CANDS)
    assert scores[1] == max(scores)


def test_el_mismo_numero_con_y_sin_espacio_cuenta_una_vez(monkeypatch):
    _fake_http(monkeypatch, _chat_response({"3": -2.0, " 3": -0.1, "1": -3.0}))
    scores = LogitChooser("http://127.0.0.1:8080").choose("x", CANDS)
    assert scores[2] == max(scores)          # se queda con el logprob mejor de los dos


def test_ignora_etiquetas_fuera_de_rango(monkeypatch):
    _fake_http(monkeypatch, _chat_response({"7": -0.1, "2": -1.0}))
    scores = LogitChooser("http://127.0.0.1:8080").choose("x", CANDS)
    assert scores[1] == 1.0 and scores[0] == 0.0


def test_la_ruta_de_respaldo_acepta_probabilidades(monkeypatch):
    """Si el servidor no da logprobs por la ruta de chat, se cae a /completion."""
    _fake_http(monkeypatch, {"completion_probabilities": [
        {"probs": [{"token": "2", "prob": 0.7}, {"token": "1", "prob": 0.3}]}]})
    scores = LogitChooser("http://127.0.0.1:8080").choose("x", CANDS)
    assert scores[1] > scores[0]


def test_un_solo_candidato_no_necesita_decision(monkeypatch):
    def no_llamar(*a, **k):
        raise AssertionError("no debería llamar al servidor con un candidato")
    monkeypatch.setattr(chooser.urllib.request, "urlopen", no_llamar)
    assert LogitChooser("http://127.0.0.1:8080").choose("x", [ART2]) == [1.0]


def test_servidor_caido_devuelve_vacio_y_anota_el_error(monkeypatch):
    def boom(*a, **k):
        raise OSError("connection refused")
    monkeypatch.setattr(chooser.urllib.request, "urlopen", boom)
    ch = LogitChooser("http://127.0.0.1:8080")
    assert ch.choose("x", CANDS) == []
    assert "connection refused" in ch.last_error


def test_respuesta_sin_probabilidades_no_revienta(monkeypatch):
    _fake_http(monkeypatch, {"choices": [{"message": {"content": "2"}}], "content": "2"})
    assert LogitChooser("http://127.0.0.1:8080").choose("x", CANDS) == []


# ── ExternalChooser: Laya, Kev, Von, SemIf, NanoJev ────────────────────────

def test_lee_una_distribucion(monkeypatch):
    _fake_http(monkeypatch, {"scores": {"1": 0.1, "2": 0.8, "3": 0.1}})
    scores = ExternalChooser("laya", "http://127.0.0.1:9101/decide").choose("x", CANDS)
    assert scores == [0.1, 0.8, 0.1]


def test_lee_solo_la_elegida(monkeypatch):
    _fake_http(monkeypatch, {"choice": "2"})
    assert ExternalChooser("von", "http://127.0.0.1:9102/decide").choose("x", CANDS) == [0.0, 1.0, 0.0]


def test_lee_la_forma_de_laya(monkeypatch):
    """Laya responde answers.<pregunta>.choice con su distribución."""
    _fake_http(monkeypatch, {"routing": {"model": "laya-en"},
                             "answers": {"cual": {"choice": "3", "probs": {"1": 0.2, "2": 0.1, "3": 0.7}}}})
    scores = ExternalChooser("laya", "http://127.0.0.1:9101/decide").choose("x", CANDS)
    assert scores[2] == 0.7


def test_lee_la_forma_de_laya_sin_distribucion(monkeypatch):
    _fake_http(monkeypatch, {"answers": {"cual": {"choice": 2}}})
    assert ExternalChooser("laya", "http://127.0.0.1:9101/decide").choose("x", CANDS) == [0.0, 1.0, 0.0]


def test_normaliza_una_distribucion_que_no_suma_uno(monkeypatch):
    _fake_http(monkeypatch, {"scores": {"1": 2.0, "2": 6.0, "3": 2.0}})
    scores = ExternalChooser("kev", "http://127.0.0.1:9103/decide").choose("x", CANDS)
    assert abs(sum(scores) - 1.0) < 1e-6 and scores[1] == 0.6


def test_respuesta_incomprensible_devuelve_vacio(monkeypatch):
    _fake_http(monkeypatch, {"resultado": "el segundo"})
    assert ExternalChooser("von", "http://127.0.0.1:9102/decide").choose("x", CANDS) == []


def test_el_estado_y_las_opciones_viajan_en_el_cuerpo(monkeypatch):
    visto = {}

    class FakeResp:
        def read(self):
            return json.dumps({"choice": "1"}).encode("utf-8")

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    def capturar(req, timeout=None):
        visto.update(json.loads(req.data))
        return FakeResp()

    monkeypatch.setattr(chooser.urllib.request, "urlopen", capturar)
    ExternalChooser("laya", "http://127.0.0.1:9101/decide").choose("¿Artículo 2?", CANDS)
    assert visto["state"] == "¿Artículo 2?"
    assert visto["type"] == "choice"
    assert [o["id"] for o in visto["options"]] == ["1", "2", "3"]
    assert visto["options"][1]["key"] == "Artículo 2"


# ── Configuración por entorno ───────────────────────────────────────────────

def test_choosers_from_env(monkeypatch):
    monkeypatch.setenv("KAMVEX_CHOOSERS",
                       "laya=http://127.0.0.1:9101/decide,von=https://von.example.com/decide,"
                       "malo=http://evil.example.com/decide")
    assert [c.name for c in choosers_from_env()] == ["laya", "von"]


def test_choosers_from_env_vacio(monkeypatch):
    monkeypatch.delenv("KAMVEX_CHOOSERS", raising=False)
    assert choosers_from_env() == []


# ── Promediar varios electores ──────────────────────────────────────────────

class Fijo:
    def __init__(self, name, scores, error=None):
        self.name, self._scores, self.last_error = name, scores, error

    def choose(self, query, candidates):
        return list(self._scores)


def test_promedia_las_distribuciones():
    d = decide("x", CANDS, [Fijo("laya", [0.1, 0.8, 0.1]), Fijo("von", [0.3, 0.6, 0.1])])
    assert d.picked == 1
    assert abs(d.scores[1] - 0.7) < 1e-9
    assert set(d.per_chooser) == {"laya", "von"}
    assert d.source == "laya+von"


def test_un_elector_caido_sale_del_promedio():
    d = decide("x", CANDS, [Fijo("laya", [0.1, 0.8, 0.1]), Fijo("nanojev", [])])
    assert d.picked == 1
    assert list(d.per_chooser) == ["laya"]


def test_un_elector_que_lanza_no_tumba_la_decision():
    class Roto:
        name = "semif"

        def choose(self, q, c):
            raise RuntimeError("sin checkpoint")

    d = decide("x", CANDS, [Roto(), Fijo("laya", [0.2, 0.7, 0.1])])
    assert d.picked == 1
    assert "sin checkpoint" in d.error


def test_si_fallan_todos_no_se_reordena_nada():
    d = decide("x", CANDS, [Fijo("laya", []), Fijo("von", [])])
    assert d.scores == [] and d.picked is None
    assert reorder(CANDS, d) == CANDS


def test_un_empate_lo_decide_el_agente_a():
    """Si nadie destaca, el orden de recuperación manda: no se toca."""
    d = decide("x", CANDS, [Fijo("laya", [0.34, 0.33, 0.33])])
    assert d.picked is None
    assert reorder(CANDS, d) == CANDS


def test_sin_electores_no_hay_decision():
    d = decide("x", CANDS, [])
    assert d.scores == [] and d.picked is None


def test_reorder_pone_al_elegido_delante_y_conserva_el_resto():
    d = Decision(scores=[0.1, 0.8, 0.1], source="laya")
    assert [c.key for c in reorder(CANDS, d)] == ["Artículo 2", "Artículo 55", "Artículo 35"]


def test_la_decision_se_puede_auditar():
    d = decide("x", CANDS, [Fijo("laya", [0.1, 0.8, 0.1]), Fijo("von", [0.2, 0.7, 0.1])])
    j = d.to_json()
    assert j["picked"] == 1 and j["source"] == "laya+von"
    assert j["per_chooser"]["laya"] == [0.1, 0.8, 0.1]
    assert abs(sum(j["scores"]) - 1.0) < 1e-3


def test_softmax_de_logprobs_reales():
    """Comprobación numérica: -0.2 contra -2.5 tiene que ser una preferencia clara."""
    _ = math
    d = LogitChooser._read_labels(_logprob_response({"1": -2.5, "2": -0.2}), 2)
    assert abs(sum(d) - 1.0) < 1e-9
    assert d[1] / d[0] > 9          # e^2.3 ≈ 10


# ── El modo Exacto no puede llamar al modelo ───────────────────────────────

def test_modo_exacto_no_invoca_al_elector(monkeypatch):
    """Exacto promete cero llamadas al LLM; el elector por logits es una pasada del LLM."""
    import server

    def no_llamar(*a, **k):
        raise AssertionError("el modo Exacto no debe elegir con el modelo")

    monkeypatch.setattr(server, "_choosers", no_llamar)
    cands, info = server._decide("x", [ART2, ART35, ART55], "statistical")
    assert info == {}
    assert [c.key for c in cands] == ["Artículo 2", "Artículo 35", "Artículo 55"]


def test_modo_anclado_si_elige(monkeypatch):
    import server
    monkeypatch.setattr(server, "_choosers", lambda: [Fijo("laya", [0.1, 0.8, 0.1])])
    cands, info = server._decide("x", [ART55, ART2, ART35], "grounded")
    assert info["picked"] == 1 and info["key"] == "Artículo 2"
    assert cands[0].key == "Artículo 2"
    assert "ms" in info


def test_sin_candidatos_suficientes_no_hay_decision(monkeypatch):
    import server
    monkeypatch.setattr(server, "_choosers", lambda: [Fijo("laya", [1.0])])
    cands, info = server._decide("x", [ART2], "grounded")
    assert info == {} and cands == [ART2]


def test_cae_a_la_ruta_cruda_si_el_chat_no_da_logprobs(monkeypatch):
    """Algunos servidores sirven /completion pero no logprobs en la ruta OpenAI."""
    vistas = []

    class FakeResp:
        def __init__(self, payload):
            self._p = payload

        def read(self):
            return json.dumps(self._p).encode("utf-8")

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    def router(req, timeout=None):
        vistas.append(req.full_url)
        if req.full_url.endswith("/v1/chat/completions"):
            return FakeResp({"choices": [{"message": {"content": "2"}}]})
        return FakeResp(_logprob_response({"2": -0.1, "1": -3.0}))

    monkeypatch.setattr(chooser.urllib.request, "urlopen", router)
    scores = LogitChooser("http://127.0.0.1:8080").choose("x", CANDS)
    assert scores[1] == max(scores)
    assert [u.rsplit("/", 1)[-1] for u in vistas] == ["completions", "completion"]


def test_el_final_del_prompt_crudo_fuerza_un_digito():
    """Medido: terminar en «es la número» no produce ni un dígito entre los 40 mejores."""
    assert chooser.COMPLETION_SUFFIX.rstrip().endswith("Opción correcta:")


def test_un_candidato_autoritativo_no_se_somete_a_votacion(monkeypatch):
    """Medido: preguntando «¿Qué dice el Artículo 2?» el elector prefirió el Artículo 200."""
    import server

    class Auth:
        authority = True
        key = "Artículo 2"
        text = "Artículo 2: Toda persona tiene derecho a la vida."
        source_id = key

    def no_llamar():
        raise AssertionError("no hay nada que decidir: la pregunta nombró el registro")

    monkeypatch.setattr(server, "_choosers", no_llamar)
    cands, info = server._decide("¿Qué dice el Artículo 2?", [Auth(), ART35, ART55], "grounded")
    assert info == {"skipped": "candidato autoritativo"}
    assert cands[0].key == "Artículo 2"


def test_el_elector_viene_apagado(monkeypatch):
    """Medido: no cambia el resultado y cuesta segundos. Se enciende a mano."""
    import server
    monkeypatch.delenv("KAMVEX_CHOOSER", raising=False)
    monkeypatch.delenv("KAMVEX_CHOOSERS", raising=False)
    monkeypatch.setattr(server, "_LLAMA_CONNECTOR", object())
    assert server._choosers() == []


def test_se_enciende_con_la_variable(monkeypatch):
    import server

    class Conn:
        base_url = "http://127.0.0.1:8080"

    monkeypatch.setenv("KAMVEX_CHOOSER", "logit")
    monkeypatch.delenv("KAMVEX_CHOOSERS", raising=False)
    monkeypatch.setattr(server, "_LLAMA_CONNECTOR", Conn())
    assert [c.name for c in server._choosers()] == ["logit"]


def test_los_electores_propios_se_encienden_solos(monkeypatch):
    """Laya y compañía no dependen de KAMVEX_CHOOSER: van por su cuenta."""
    import server
    monkeypatch.delenv("KAMVEX_CHOOSER", raising=False)
    monkeypatch.setenv("KAMVEX_CHOOSERS", "laya=http://127.0.0.1:9101/decide")
    monkeypatch.setattr(server, "_LLAMA_CONNECTOR", None)
    assert [c.name for c in server._choosers()] == ["laya"]
