"""Agente B: resolver la pregunta contra la conversación, elegir candidato y redactar.

Las preguntas de aquí son las que fallaban en la app: "dame más explicación",
"y el artículo 35?", "hazme una explicación muy larga de la palabra pene".
"""

from agent_b import (
    build_context,
    is_followup,
    last_topic,
    looks_like_refusal,
    messages,
    picked_candidate,
    rewrite_query,
    wants_more_detail,
)


class C:
    """Candidato mínimo con la interfaz que consume Agente B."""

    def __init__(self, key, text, score=1.0):
        self.key, self.text, self.score = key, text, score
        self.source_id = key


PENE = C("pene", "pene: Órgano masculino de la cópula y de la micción, formado por dos cuerpos "
                 "cavernosos y el cuerpo esponjoso que aloja la uretra.")
EFIMERO = C("efímero", "efímero: Que dura un solo día. Pasajero, de corta duración.")
ART35 = C("Artículo 35", "Artículo 35: Los ciudadanos pueden ejercer sus derechos individualmente "
                         "o a través de organizaciones políticas.")


# ── Detección de seguimiento ────────────────────────────────────────────────

def test_preguntas_de_seguimiento_de_las_capturas():
    for q in ["dame mas explicacion", "dame más explicación", "dame una explicación detallada",
              "explicame eso", "amplía", "resume eso", "más",
              "explícalo de nuevo", "¿qué más?"]:
        assert is_followup(q), q


def test_pregunta_con_tema_propio_no_es_seguimiento():
    for q in ["¿Qué significa efímero?", "explicame que es Pene",
              "hazme una explicacion muy larga de la palabra pene",
              "¿Qué dice el Artículo 35 de la Constitución?",
              "explícame mis derechos fundamentales según la Constitución"]:
        assert not is_followup(q), q


def test_y_el_articulo_35_es_tema_nuevo_no_seguimiento():
    """Suena a continuación, pero nombra su propio tema: no debe reescribirse."""
    hist = [{"role": "user", "content": "¿Qué dice el Artículo 2?"},
            {"role": "assistant", "content": "Toda persona tiene derecho a la vida."}]
    assert not is_followup("y el artículo 35?")
    assert rewrite_query("y el artículo 35?", hist) == ("y el artículo 35?", {"rewritten": False})


def test_cadena_vacia_no_es_seguimiento():
    assert not is_followup("")
    assert not is_followup("   ")


# ── Reescritura contra el historial ─────────────────────────────────────────

def test_reescribe_el_seguimiento_al_tema_anterior():
    """El fallo exacto de la captura: "dame más explicación" buscaba *explicación*."""
    hist = [{"role": "user", "content": "¿Qué significa efímero?"},
            {"role": "assistant", "content": "Que dura un solo día."}]
    q, info = rewrite_query("dame mas explicacion", hist)
    assert q == "¿Qué significa efímero?"
    assert info == {"rewritten": True, "from": "dame mas explicacion",
                    "topic": "¿Qué significa efímero?"}


def test_no_reescribe_una_pregunta_con_su_propio_tema():
    hist = [{"role": "user", "content": "¿Qué significa efímero?"}]
    q, info = rewrite_query("explicame que es Pene", hist)
    assert q == "explicame que es Pene"
    assert info["rewritten"] is False


def test_sin_historial_no_hay_nada_que_reescribir():
    q, info = rewrite_query("dame mas explicacion", [])
    assert q == "dame mas explicacion" and info["rewritten"] is False


def test_seguimiento_sin_tema_previo_se_deja_igual():
    hist = [{"role": "user", "content": "dame mas"}, {"role": "assistant", "content": "¿de qué?"}]
    q, info = rewrite_query("amplía", hist)
    assert q == "amplía"
    assert info["reason"] == "sin tema previo"


def test_salta_los_seguimientos_para_encontrar_el_tema():
    hist = [{"role": "user", "content": "¿Qué es el ceviche?"},
            {"role": "assistant", "content": "Un plato de pescado marinado."},
            {"role": "user", "content": "dame más"},
            {"role": "assistant", "content": "Se prepara con limón."}]
    assert last_topic(hist) == "¿Qué es el ceviche?"
    assert rewrite_query("y más ejemplos", hist)[0] == "¿Qué es el ceviche?"


# ── Nivel de detalle ────────────────────────────────────────────────────────

def test_detecta_cuando_piden_mas_detalle():
    assert wants_more_detail("hazme una explicacion muy larga de la palabra pene")
    assert wants_more_detail("dame una explicación detallada")
    assert wants_more_detail("dame mas explicacion")
    assert not wants_more_detail("¿Qué significa efímero?")
    assert not wants_more_detail("Artículo 35")


def test_el_prompt_pide_profundidad_solo_cuando_toca():
    largo = messages("hazme una explicacion muy larga de la palabra pene", [PENE])[0]["content"]
    breve = messages("¿Qué significa efímero?", [EFIMERO])[0]["content"]
    assert "aprovecha todo lo relevante de los candidatos" in largo
    assert "Sé breve" in breve


def test_pedir_mas_detalle_prohibe_rellenar_con_lo_que_sepa_el_modelo():
    """Una definición de cuatro palabras no da para una explicación larga: hay que decirlo."""
    system = messages("hazme una explicacion muy larga de la palabra pene", [PENE])[0]["content"]
    assert "no recogen nada más" in system
    assert "Nunca rellenes" in system


def test_el_prompt_prohibe_repetir_la_respuesta_anterior():
    system = messages("¿Qué dice el Artículo 2?", [ART35])[0]["content"]
    assert "No repitas tu respuesta anterior" in system


# ── Construcción del contexto y del prompt ──────────────────────────────────

def test_el_contexto_numera_los_candidatos_con_su_clave():
    ctx = build_context([PENE, EFIMERO], "que es pene?")
    assert ctx.startswith("[1] (pene)")
    assert "[2] (efímero)" in ctx


def test_el_contexto_recorta_los_candidatos_largos():
    largo = C("x", "relleno irrelevante. " * 200 + " El dato clave es la uretra.")
    ctx = build_context([largo], "uretra", chars=200)
    assert len(ctx) < 400
    assert "uretra" in ctx


def test_el_contexto_respeta_el_maximo_de_candidatos():
    cands = [C(f"k{i}", f"texto {i}") for i in range(10)]
    ctx = build_context(cands, "texto", max_candidates=3)
    assert "[3]" in ctx and "[4]" not in ctx


def test_el_prompt_lleva_reglas_candidatos_y_pregunta():
    msgs = messages("explicame que es Pene", [PENE, EFIMERO])
    assert msgs[0]["role"] == "system" and msgs[-1]["role"] == "user"
    system, user = msgs[0]["content"], msgs[-1]["content"]
    assert "ÚNICAMENTE los CANDIDATOS" in system
    assert "Elige el candidato que responde" in system
    assert "Nunca añadas datos" in system
    assert "La información disponible no cubre este tema." in system
    assert "CANDIDATOS:" in user and "PREGUNTA: explicame que es Pene" in user
    assert "cópula" in user


def test_el_prompt_del_experto_se_antepone_a_las_reglas():
    msgs = messages("Artículo 35", [ART35], system_extra="Eres un asistente jurídico.")
    assert msgs[0]["content"].startswith("Eres un asistente jurídico.")


def test_el_prompt_incluye_la_conversacion_cuando_la_pregunta_la_necesita():
    hist = [{"role": "user", "content": "¿Qué significa efímero?"},
            {"role": "assistant", "content": "Que dura un solo día."}]
    msgs = messages("dame más", [EFIMERO], history=hist)
    assert [m["role"] for m in msgs] == ["system", "user", "assistant", "user"]
    assert msgs[1]["content"] == "¿Qué significa efímero?"


def test_una_pregunta_con_tema_propio_no_arrastra_la_conversacion():
    """Un modelo pequeño se engancha al turno anterior y lo repite: mejor no dárselo."""
    hist = [{"role": "user", "content": "y el artículo 35?"},
            {"role": "assistant", "content": "El artículo 35 habla de organizaciones políticas."}]
    msgs = messages("¿Qué dice el Artículo 2?", [ART35], history=hist)
    assert [m["role"] for m in msgs] == ["system", "user"]
    assert "organizaciones políticas" not in msgs[0]["content"]


def test_la_conversacion_se_limita_a_los_ultimos_turnos():
    hist = [{"role": "user" if i % 2 == 0 else "assistant", "content": f"turno {i}"}
            for i in range(20)]
    msgs = messages("dame más", [EFIMERO], history=hist)
    assert len(msgs) == 2 + 6                       # system + 6 turnos + user
    assert "turno 19" in msgs[-2]["content"]


def test_los_turnos_vacios_o_de_sistema_no_entran():
    hist = [{"role": "system", "content": "no"}, {"role": "user", "content": "  "},
            {"role": "user", "content": "sí"}]
    msgs = messages("dame más", [EFIMERO], history=hist)
    assert [m["content"] for m in msgs[1:-1]] == ["sí"]


def test_prompt_en_ingles():
    system = messages("what is a penis?", [PENE], language="en")[0]["content"]
    assert "ONLY the CANDIDATES" in system
    assert "does not cover this topic" in system


# ── Qué candidato usó la respuesta ──────────────────────────────────────────

def test_identifica_el_candidato_parafraseado():
    answer = ("El pene es el órgano masculino de la cópula y de la micción; lo forman dos "
              "cuerpos cavernosos y el cuerpo esponjoso, que aloja la uretra.")
    assert picked_candidate(answer, [EFIMERO, PENE]) == 1


def test_una_respuesta_inventada_no_apunta_a_ningun_candidato():
    assert picked_candidate("Lima fue fundada en 1535 por Francisco Pizarro.",
                            [EFIMERO, PENE]) is None


def test_respuesta_vacia_no_apunta_a_nada():
    assert picked_candidate("", [PENE]) is None
    assert picked_candidate("   ...   ", [PENE]) is None


# ── Negativa ────────────────────────────────────────────────────────────────

def test_reconoce_la_negativa_en_ambos_idiomas():
    assert looks_like_refusal("La información disponible no cubre este tema.")
    assert looks_like_refusal("Lo siento, la información disponible NO CUBRE ESTE TEMA")
    assert looks_like_refusal("The available information does not cover this topic.")
    assert not looks_like_refusal("El pene es el órgano masculino de la cópula.")
