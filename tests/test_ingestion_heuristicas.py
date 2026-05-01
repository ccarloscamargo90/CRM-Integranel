"""Tests de heurísticas de ingestión (sin DB)."""

from __future__ import annotations

from src.core.heuristicas import (
    canales_iniciales_de_scian,
    estrato_a_empleados,
    hash_dedup,
    normaliza_nombre,
    scian_desde_clee,
    tipo_establecimiento_de_scian,
    volumen_estimado_ton_mes,
)

# ---------- normaliza_nombre ----------


def test_normaliza_lowercase():
    assert normaliza_nombre("TORTILLERIA") == "tortilleria"


def test_normaliza_quita_acentos():
    assert normaliza_nombre("Tortillería") == "tortilleria"


def test_normaliza_colapsa_espacios():
    assert normaliza_nombre("La  Esperanza   S.A.") == "la esperanza s a"


def test_normaliza_quita_signos():
    assert normaliza_nombre("Don Pepe's Tortillería, S.A. de C.V.") == "don pepe s tortilleria s a de c v"


def test_normaliza_none_es_string_vacio():
    assert normaliza_nombre(None) == ""
    assert normaliza_nombre("") == ""


def test_normaliza_idempotente():
    s = normaliza_nombre("Café Olé!")
    assert normaliza_nombre(s) == s


# ---------- hash_dedup ----------


def test_hash_dedup_es_determinista():
    h1 = hash_dedup("Tortillería La Higiénica", "06090", 19.43, -99.13)
    h2 = hash_dedup("Tortillería La Higiénica", "06090", 19.43, -99.13)
    assert h1 == h2
    assert len(h1) == 40  # sha1 hex


def test_hash_dedup_es_sensible_a_nombre():
    h1 = hash_dedup("A", "01", 1.0, 1.0)
    h2 = hash_dedup("B", "01", 1.0, 1.0)
    assert h1 != h2


def test_hash_dedup_redondea_coords():
    """Diferencias < 1e-4 deben colisionar (mismo establecimiento, ruido GPS)."""
    h1 = hash_dedup("Tort", "01", 19.43001, -99.13001)
    h2 = hash_dedup("Tort", "01", 19.43002, -99.13003)
    assert h1 == h2  # ambos redondean a 19.4300, -99.1300


def test_hash_dedup_acepta_coords_none():
    h = hash_dedup("Tort", "01", None, None)
    assert isinstance(h, str)


# ---------- estrato_a_empleados ----------


def test_estrato_conocido():
    assert estrato_a_empleados("0 a 5 personas") == 3
    assert estrato_a_empleados("251 y más personas") == 350


def test_estrato_desconocido_o_nulo():
    assert estrato_a_empleados(None) is None
    assert estrato_a_empleados("") is None
    assert estrato_a_empleados("texto inventado") is None


# ---------- tipo_establecimiento_de_scian ----------


def test_tipo_311830_default_tortilleria_tradicional():
    assert tipo_establecimiento_de_scian("311830", "El Trigo") == "tortilleria_tradicional"


def test_tipo_311830_con_molino():
    assert tipo_establecimiento_de_scian("311830", "Molino Don Pepe") == "molino_nixtamal"


def test_tipo_311830_moderna():
    assert (
        tipo_establecimiento_de_scian("311830", "Tortillería Moderna del Centro")
        == "tortilleria_moderna"
    )


def test_tipo_813110_union_ganadera():
    assert (
        tipo_establecimiento_de_scian("813110", "Unión Ganadera Regional de Veracruz")
        == "union_ganadera_regional"
    )


def test_tipo_311110_es_fabricante_industrial():
    assert tipo_establecimiento_de_scian("311110", "Bachoco SA") == "fabricante_industrial"


def test_tipo_scian_desconocido():
    assert tipo_establecimiento_de_scian("999999", "Cualquiera") == "desconocido"


# ---------- volumen_estimado_ton_mes ----------


def test_volumen_tortilleria_tradicional():
    # 3 empleados × 1.8 ratio = 5.4
    assert volumen_estimado_ton_mes("tortilleria_tradicional", 3) == 5.4


def test_volumen_fabricante_industrial():
    # 175 empleados × 50.0 ratio = 8750
    assert volumen_estimado_ton_mes("fabricante_industrial", 175) == 8750.0


def test_volumen_devuelve_none_sin_inputs():
    assert volumen_estimado_ton_mes(None, 5) is None
    assert volumen_estimado_ton_mes("tortilleria_tradicional", None) is None


# ---------- canales_iniciales_de_scian ----------


def test_canales_311830_es_tortillerias():
    assert canales_iniciales_de_scian("311830") == ["Tortillerias"]


def test_canales_311110_es_alimento_balanceado():
    assert canales_iniciales_de_scian("311110") == ["AlimentoBalanceado"]


def test_canales_434112_es_forrajeras():
    assert canales_iniciales_de_scian("434112") == ["ForrajerasPecuario"]


def test_canales_scian_desconocido_lista_vacia():
    assert canales_iniciales_de_scian("999999") == []


# ---------- scian_desde_clee ----------


def test_scian_desde_clee_valido():
    # ejemplo real: 15068813110000042000000000U6 → SCIAN 813110
    clee = "15068813110000042000000000U6"
    assert scian_desde_clee(clee) == "813110"


def test_scian_desde_clee_corto():
    assert scian_desde_clee("123") is None


def test_scian_desde_clee_none():
    assert scian_desde_clee(None) is None
