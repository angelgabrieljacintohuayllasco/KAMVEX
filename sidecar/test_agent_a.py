"""Agente A: el ensemble propone candidatos y la fusión premia el acuerdo."""

import json

import agent_a
from agent_a import (
    Candidate,
    ExternalPredictor,
    KeyPredictor,
    LexicalPredictor,
    fuse,
    predictors_from_env,
    run_ensemble,
)
from keyindex import KeyIndex

RECORDS = {
    "Artículo 2": {"key": "Artículo 2", "text": "Toda persona tiene derecho a la vida, a su "
                                                "identidad, a su integridad moral, psíquica y física."},
    "Artículo 35": {"key": "Artículo 35", "text": "Los ciudadanos pueden ejercer sus derechos "
                                                  "individualmente o a través de organizaciones políticas."},
    "pene": {"key": "pene", "text": "Órgano masculino de la cópula y de la micción."},
    "y": {"key": "y", "text": "Conjunción copulativa que une palabras o cláusulas."},
}


class FakeReader:
    """Sustituye al lector de SHARD: devuelve el JSON crudo de un registro."""

    def __init__(self, records=None):
        self.records = records if records is not None else RECORDS

    def find(self, key):
        rec = self.records.get(key)
        return json.dumps(rec, ensure_ascii=False) if rec else None


def _to_text(record):
    return f"{record['key']}: {record['text']}"


def _index():
    return KeyIndex(list(RECORDS))


def _cand(key, score=1.0, source="x"):
    return Candidate(key=key, text=f"texto de {key}", sources={source: score})


# ── Fusión ──────────────────────────────────────────────────────────────────

def test_fuse_premia_el_acuerdo_entre_predictores():
    """Lo que dos predictores proponen gana a lo que solo uno pone primero."""
    ranked = fuse({
        "semantic": [_cand("B", source="semantic"), _cand("A", source="semantic")],
        "key": [_cand("A", source="key")],
    }, top_k=5)
    assert [c.key for c in ranked][0] == "A"
    a = ranked[0]
    assert a.agreement == 2
    assert set(a.sources) == {"semantic", "key"}


def test_fuse_sin_acuerdo_respeta_el_orden_original():
    ranked = fuse({"semantic": [_cand("A"), _cand("B"), _cand("C")]}, top_k=3)
    assert [c.key for c in ranked] == ["A", "B", "C"]
    assert ranked[0].score == 1.0            # normalizado al mejor


def test_fuse_conserva_el_texto_mas_completo():
    corto = Candidate(key="A", text="corto", sources={"key": 1.0})
    largo = Candidate(key="A", text="un texto bastante más completo", sources={"semantic": 0.8})
    ranked = fuse({"key": [corto], "semantic": [largo]}, top_k=1)
    assert ranked[0].text == "un texto bastante más completo"


def test_fuse_vacio_no_revienta():
    assert fuse({}, top_k=5) == []
    assert fuse({"semantic": []}, top_k=5) == []


def test_fuse_registra_la_posicion_de_cada_predictor():
    ranked = fuse({"semantic": [_cand("A"), _cand("B")], "key": [_cand("B")]}, top_k=2)
    b = next(c for c in ranked if c.key == "B")
    assert b.ranks == {"semantic": 1, "key": 0}


def test_candidate_expone_la_interfaz_de_fragment():
    c = Candidate(key="Artículo 2", text="…", sources={"key": 1.0})
    assert c.source_id == "Artículo 2"       # lo que espera grounding/_fragments_json
    assert c.to_json()["predictors"] == {"key": 1.0}


# ── Predictores locales ─────────────────────────────────────────────────────

def test_key_predictor_devuelve_el_registro_nombrado():
    p = KeyPredictor(_index(), FakeReader(), _to_text)
    out = p.predict("¿Qué dice el Artículo 35?", 5)
    assert out and out[0].key == "Artículo 35"
    assert "organizaciones políticas" in out[0].text


def test_key_predictor_ignora_la_conjuncion_en_preguntas_largas():
    """"y el artículo 35?" no debe devolver la entrada del diccionario para *y*."""
    p = KeyPredictor(_index(), FakeReader(), _to_text)
    keys = [c.key for c in p.predict("y el artículo 35?", 5)]
    assert keys[0] == "Artículo 35"
    assert "y" not in keys


def test_lexical_predictor_puntua_por_palabras_de_contenido():
    p = LexicalPredictor(_index(), FakeReader(), _to_text)
    out = p.predict("artículo 2", 3)
    assert out and out[0].key == "Artículo 2"
    assert p.predict("xilófono cuántico", 3) == []


def test_lexical_predictor_sin_terminos_utiles_no_propone_nada():
    p = LexicalPredictor(_index(), FakeReader(), _to_text)
    assert p.predict("de la", 3) == []


# ── Predictor externo (Laya, Kev, Von, SemIf, NanoJev, jevlike…) ────────────

def test_external_predictor_parsea_la_respuesta(monkeypatch):
    payload = {"candidates": [{"key": "pene", "score": 0.93},
                              {"text": "algo suelto sin clave", "score": 0.4}]}
    _fake_http(monkeypatch, payload)
    p = ExternalPredictor("laya", "http://127.0.0.1:9001/predict", FakeReader(), _to_text)
    out = p.predict("que es pene?", 5)
    assert [c.key for c in out] == ["pene", "laya-1"]
    assert "cópula" in out[0].text          # texto resuelto desde el corpus por la clave
    assert out[0].sources == {"laya": 0.93}


def test_external_predictor_acepta_una_lista_pelada(monkeypatch):
    _fake_http(monkeypatch, [{"key": "pene", "text": "definición", "score": 0.5}])
    p = ExternalPredictor("kev", "http://127.0.0.1:9002/predict")
    assert [c.key for c in p.predict("pene", 3)] == ["pene"]


def test_external_predictor_caido_no_tumba_el_ensemble(monkeypatch):
    def boom(*a, **k):
        raise OSError("connection refused")
    monkeypatch.setattr(agent_a.urllib.request, "urlopen", boom)
    externo = ExternalPredictor("von", "http://127.0.0.1:9003/predict")
    local = KeyPredictor(_index(), FakeReader(), _to_text)
    cands, diag = run_ensemble([externo, local], "Artículo 2", top_k=3)
    assert [c.key for c in cands] == ["Artículo 2"]
    assert diag["predictors"]["von"] == {"n": 0, "top": None, "error": "connection refused"}


def test_predictor_que_lanza_excepcion_queda_registrado():
    class Roto:
        name = "nanojev"

        def predict(self, query, k):
            raise RuntimeError("modelo sin cargar")

    cands, diag = run_ensemble([Roto(), KeyPredictor(_index(), FakeReader(), _to_text)],
                               "Artículo 2", top_k=3)
    assert cands and cands[0].key == "Artículo 2"
    assert "modelo sin cargar" in diag["predictors"]["nanojev"]["error"]


def _fake_http(monkeypatch, payload):
    class FakeResp:
        def read(self):
            return json.dumps(payload).encode("utf-8")

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    monkeypatch.setattr(agent_a.urllib.request, "urlopen", lambda req, timeout=None: FakeResp())


# ── Configuración por entorno ───────────────────────────────────────────────

def test_predictors_from_env_registra_los_modelos_del_usuario(monkeypatch):
    monkeypatch.setenv("KAMVEX_PREDICTORS",
                       "laya=http://127.0.0.1:9001/predict, kev=http://localhost:9002/predict,"
                       "jevlike=https://jev.example.com/predict")
    names = [p.name for p in predictors_from_env(dataset="diccionario-es")]
    assert names == ["laya", "kev", "jevlike"]
    assert predictors_from_env()[0].dataset == ""


def test_predictors_from_env_rechaza_http_no_loopback(monkeypatch):
    monkeypatch.setenv("KAMVEX_PREDICTORS", "malo=http://evil.example.com/predict,"
                                            "sinurl=,roto")
    assert predictors_from_env() == []


def test_predictors_from_env_vacio_por_defecto(monkeypatch):
    monkeypatch.delenv("KAMVEX_PREDICTORS", raising=False)
    assert predictors_from_env() == []


# ── Ensemble completo ───────────────────────────────────────────────────────

def test_run_ensemble_devuelve_candidatos_y_diagnostico():
    idx, reader = _index(), FakeReader()
    cands, diag = run_ensemble([KeyPredictor(idx, reader, _to_text),
                                LexicalPredictor(idx, reader, _to_text)],
                               "¿Qué dice el Artículo 2?", top_k=3)
    assert cands[0].key == "Artículo 2"
    assert cands[0].agreement == 2                      # ambos predictores coinciden
    assert diag["predictors"]["key"]["top"] == "Artículo 2"
    assert diag["predictors"]["lexical"]["n"] >= 1


# ── Predictor de texto (BM25 sobre el contenido, no sobre las claves) ───────

TEXT_RECORDS = [
    {"key": "Artículo 2", "text": "Toda persona tiene derecho a la vida, a la igualdad ante la ley, "
                                  "a la libertad de conciencia, a la libertad de expresión, al honor, "
                                  "a la propiedad, a la herencia y a la legítima defensa. " * 6},
    {"key": "Artículo 55", "text": "Los tratados celebrados por el Estado y en vigor forman parte "
                                   "del derecho nacional."},
    {"key": "Artículo 107", "text": "El Presidente de la República tiene derecho de iniciativa en "
                                    "la formación de las leyes."},
]


def _text_predictor(records=None):
    recs = records if records is not None else TEXT_RECORDS
    return agent_a.TextPredictor([r["key"] for r in recs], recs, lambda r: r["text"])


def test_text_predictor_encuentra_lo_que_no_se_nombra_por_su_clave():
    """"explícame mis derechos" no nombra ningún registro; BM25 sobre el texto sí lo halla."""
    p = _text_predictor()
    assert [c.key for c in p.predict("explícame mis derechos", 2)][0] == "Artículo 2"
    assert p.predict("libertad de expresión", 1)[0].key == "Artículo 2"
    assert p.predict("tratados internacionales", 1)[0].key == "Artículo 55"


def test_el_tope_de_longitud_sube_el_score_del_registro_largo():
    """BM25 clásico entierra el artículo largo que enumera 32 derechos; el tope lo rescata."""
    p = _text_predictor()
    largo = p.keys.index("Artículo 2")
    terms = agent_a.content_tokens("mis derechos")
    con_tope = p.bm25(terms)[largo]
    p.LENGTH_CLAMP = 1e9                      # BM25 clásico, sin tope
    try:
        sin_tope = p.bm25(terms)[largo]
    finally:
        del p.LENGTH_CLAMP
    assert con_tope > sin_tope, "el tope debe aliviar el castigo por longitud"
    # El corto no se mueve: su longitud ya está por debajo del tope.
    corto = p.keys.index("Artículo 107")
    p.LENGTH_CLAMP = 1e9
    try:
        corto_sin_tope = p.bm25(terms)[corto]
    finally:
        del p.LENGTH_CLAMP
    assert p.bm25(terms)[corto] == corto_sin_tope


def test_text_predictor_sin_terminos_conocidos_no_propone_nada():
    p = _text_predictor()
    assert p.predict("xilófono cuántico", 3) == []
    assert p.predict("", 3) == []


def test_text_predictor_desde_los_ficheros_del_dataset(tmp_path):
    (tmp_path / "keys.json").write_text(json.dumps([r["key"] for r in TEXT_RECORDS]), encoding="utf-8")
    (tmp_path / "records.json").write_text(json.dumps(TEXT_RECORDS, ensure_ascii=False), encoding="utf-8")
    p = agent_a.TextPredictor.from_dataset(tmp_path, lambda r: r["text"])
    assert p is not None and len(p) == 3
    assert p.predict("tratados", 1)[0].key == "Artículo 55"


def test_text_predictor_sin_ficheros_devuelve_none(tmp_path):
    assert agent_a.TextPredictor.from_dataset(tmp_path, lambda r: r["text"]) is None
    (tmp_path / "keys.json").write_text("no es json", encoding="utf-8")
    (tmp_path / "records.json").write_text("[]", encoding="utf-8")
    assert agent_a.TextPredictor.from_dataset(tmp_path, lambda r: r["text"]) is None


# ── Autoridad: el acierto exacto no se deja tapar ───────────────────────────

def test_el_acierto_exacto_manda_sobre_dos_predictores_que_coinciden():
    """El fallo real: semantic+lexical coincidían en «pendiente» y tapaban «pene»."""
    idx = KeyIndex(["pene", "pendiente"])
    key = KeyPredictor(idx, FakeReader({"pene": RECORDS["pene"],
                                        "pendiente": {"key": "pendiente", "text": "Que pende."}}),
                       _to_text)
    ruido = [Candidate(key="pendiente", text="Que pende.", sources={"semantic": 0.6})]
    ranked = fuse({"key": key.predict("explicame que es Pene", 3),
                   "semantic": ruido,
                   "lexical": list(ruido)}, top_k=2)
    assert ranked[0].key == "pene"
    assert ranked[0].authority is True and ranked[0].score == 1.0
    assert ranked[0].to_json()["authority"] is True


def test_solo_el_primer_acierto_exacto_es_autoritativo():
    """Una pregunta larga puede nombrar varias claves; solo la mejor es certeza."""
    idx = KeyIndex(["pene", "palabra"])
    key = KeyPredictor(idx, FakeReader({"pene": RECORDS["pene"],
                                        "palabra": {"key": "palabra", "text": "Unidad léxica."}}),
                       _to_text)
    out = key.predict("hazme una explicacion larga de la palabra pene", 3)
    assert [c.authority for c in out] == [True] + [False] * (len(out) - 1)


def test_una_coincidencia_por_prefijo_no_es_autoritativa():
    idx = KeyIndex(["Departamento de Amazonas (Perú)"])
    key = KeyPredictor(idx, FakeReader({"Departamento de Amazonas (Perú)":
                                        {"key": "x", "text": "Región del norte."}}), _to_text)
    out = key.predict("capital del departamento de Amazonas", 3)
    assert out and out[0].authority is False
