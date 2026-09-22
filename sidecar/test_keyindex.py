from keyindex import KeyIndex


def _idx():
    return KeyIndex([
        "Artículo 1", "Artículo 2", "Artículo 20", "Artículo 55", "Artículo 206",
        "Departamento de Amazonas (Perú)", "Departamento de Amazonas (Confederación Perú-Boliviana)",
        "Departamento de Amazonas (Colombia)", "Diabetes", "Diabetes tipo 2", "efémero", "huevo", "huevo frito",
        "huevo#1",
    ])


def test_exact_ngram_beats_partial_numbers():
    idx = _idx()
    assert idx.match("¿Qué dice el Artículo 2 de la Constitución sobre la igualdad?") == ["Artículo 2"]
    assert idx.match("artículo 20") == ["Artículo 20"]
    assert idx.match("El ARTÍCULO 206 habla de la reforma") == ["Artículo 206"]


def test_longest_match_wins():
    idx = _idx()
    assert idx.match("¿Qué es la diabetes tipo 2?")[0] == "Diabetes tipo 2"
    assert idx.match("¿Qué es la diabetes?") == ["Diabetes"]
    assert idx.match("¿Qué es un huevo frito?")[0] == "huevo frito"


def test_prefix_match_prefers_shortest_key():
    idx = _idx()
    hits = idx.match("¿Cuál es la capital del departamento de Amazonas?")
    assert hits[0] == "Departamento de Amazonas (Perú)"
    assert "Departamento de Amazonas (Colombia)" in hits


def test_fuzzy_single_word_and_accents():
    idx = _idx()
    assert idx.match("¿Qué significa efímero?") == ["efémero"]
    assert idx.match("que significa efimero") == ["efémero"]
    assert idx.match("¿Qué es huevo?") and idx.match("¿Qué es huevo?")[0] in ("huevo", "huevo#1")


def test_no_match():
    idx = _idx()
    assert idx.match("hola cómo estás") == []
    assert idx.match("") == []
