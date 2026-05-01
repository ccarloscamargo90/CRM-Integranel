"""Tests de los componentes de scoring (sin DB)."""

from __future__ import annotations

from src.enrichment.scoring import (
    BONUS_ETIQUETAS,
    PESOS_POR_CANAL,
    _puntaje_antiguedad,
    _puntaje_cadena,
    _puntaje_consumo,
    _puntaje_contacto,
    _puntaje_pobreza_inversa,
    _puntaje_produccion_maiz,
    _puntaje_tamano,
    _puntaje_volumen_google,
)


def test_puntaje_tamano_estrato_alto_da_score_alto():
    assert _puntaje_tamano(350) > _puntaje_tamano(3)
    assert _puntaje_tamano(None) == 0


def test_puntaje_antiguedad_escala():
    assert _puntaje_antiguedad(2010) == 100  # 16 años, ≥10
    assert _puntaje_antiguedad(2020) == 70   # 6 años, en [5,10)
    assert _puntaje_antiguedad(2024) == 40   # 2 años, en [2,5)
    assert _puntaje_antiguedad(2025) == 20
    assert _puntaje_antiguedad(None) == 0


def test_puntaje_volumen_google_sin_data():
    assert _puntaje_volumen_google(None, None) == 0
    assert _puntaje_volumen_google(4.5, 0) == 0


def test_puntaje_volumen_google_con_data():
    """5 estrellas con muchos reviews → score muy alto."""
    score_alto = _puntaje_volumen_google(5.0, 1000)
    score_bajo = _puntaje_volumen_google(3.0, 5)
    assert score_alto > score_bajo
    assert 0 < score_alto <= 100


def test_puntaje_pobreza_inversa_invierte():
    # Menor pobreza → score más alto (mayor capacidad de compra)
    score_rica = _puntaje_pobreza_inversa(24)  # CDMX/AGS
    score_pobre = _puntaje_pobreza_inversa(67)  # Chiapas
    assert score_rica > score_pobre
    assert _puntaje_pobreza_inversa(None) == 50


def test_puntaje_contacto_suma_factores():
    class _E:
        telefono = None
        direccion = None
        email = None
        sitio_web = None

    e = _E()
    assert _puntaje_contacto(e) == 0

    e.telefono = "5512345678"
    assert _puntaje_contacto(e) == 40

    e.direccion = "Calle X 100"
    assert _puntaje_contacto(e) == 70

    e.email = "test@example.com"
    assert _puntaje_contacto(e) == 100


def test_puntaje_cadena_escalas():
    assert _puntaje_cadena(None) == 0
    assert _puntaje_cadena(1) == 0
    assert _puntaje_cadena(3) == 30
    assert _puntaje_cadena(15) == 50
    assert _puntaje_cadena(25) == 70
    assert _puntaje_cadena(100) == 100


def test_puntaje_produccion_maiz_logaritmico():
    """Estado productor (1.7M ton) debe tener score alto. CDMX (4K) bajo."""
    score_prod = _puntaje_produccion_maiz(1_700_000)
    score_bajo = _puntaje_produccion_maiz(4000)
    assert score_prod > score_bajo


def test_puntaje_consumo_per_capita():
    """Mayor consumo → mayor score."""
    s_alto = _puntaje_consumo(92)  # Oaxaca
    s_bajo = _puntaje_consumo(67)  # Quintana Roo
    assert s_alto > s_bajo
    assert _puntaje_consumo(None) == 50


def test_pesos_por_canal_definidos_para_los_4_canales():
    canales_esperados = {
        "Tortillerias", "AlimentoBalanceado",
        "ForrajerasPecuario", "AsociacionesAgropecuarias",
    }
    assert set(PESOS_POR_CANAL.keys()) == canales_esperados


def test_pesos_suman_100_aprox():
    """Los pesos base de cada canal deben sumar ~100 (sin contar bonus)."""
    for canal, pesos in PESOS_POR_CANAL.items():
        total = sum(pesos.values())
        assert 95 <= total <= 105, f"Canal {canal} suma {total}, esperado ~100"


def test_bonus_etiquetas_no_negativos():
    for bonus in BONUS_ETIQUETAS.values():
        assert bonus > 0
