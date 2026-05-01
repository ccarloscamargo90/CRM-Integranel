"""Tests del matcher DENUE↔Google Places (sin red real, sin DB)."""

from __future__ import annotations

from src.enrichment.matching import (
    _haversine_m,
    construir_query,
    evaluar_candidatos,
)


class _FakeEst:
    """Mínimo establecimiento para no requerir DB."""

    def __init__(
        self,
        nombre: str = "Tortillería La Esperanza",
        nombre_norm: str = "tortilleria la esperanza",
        colonia: str | None = "Centro",
        estado: str | None = "Querétaro",
        latitud: float | None = 20.59,
        longitud: float | None = -100.39,
    ):
        self.nombre = nombre
        self.nombre_norm = nombre_norm
        self.colonia = colonia
        self.estado = estado
        self.latitud = latitud
        self.longitud = longitud


def test_haversine_simetrico():
    a = _haversine_m(20.0, -100.0, 20.001, -100.0)
    b = _haversine_m(20.001, -100.0, 20.0, -100.0)
    assert abs(a - b) < 1e-6


def test_haversine_aprox_111m_por_grado_lat():
    # 0.001 grados de latitud ≈ 111 m
    d = _haversine_m(20.0, -100.0, 20.001, -100.0)
    assert 100 < d < 120


def test_haversine_mismo_punto_es_cero():
    d = _haversine_m(19.43, -99.13, 19.43, -99.13)
    assert d < 1e-3


def test_construir_query_concatena():
    q = construir_query(_FakeEst())
    assert "Tortillería La Esperanza" in q
    assert "Centro" in q
    assert "Querétaro" in q


def test_evaluar_candidatos_score_perfecto():
    """Mismo nombre, misma ubicación → score muy alto."""
    est = _FakeEst()
    candidatos = [
        {
            "id": "ChIJ_test_1",
            "displayName": {"text": "Tortillería La Esperanza"},
            "location": {"latitude": 20.59, "longitude": -100.39},
        }
    ]
    evals = evaluar_candidatos(est, candidatos)
    assert len(evals) == 1
    assert evals[0].score >= 95
    assert evals[0].distancia_m < 1


def test_evaluar_candidatos_descarta_lejano():
    """Mismo nombre pero a 5 km → score bajo por distancia."""
    est = _FakeEst()
    candidatos = [
        {
            "id": "ChIJ_far",
            "displayName": {"text": "Tortillería La Esperanza"},
            "location": {"latitude": 20.64, "longitude": -100.39},  # ~5 km al norte
        }
    ]
    evals = evaluar_candidatos(est, candidatos)
    # Score nombre 100, score prox 0 → 0.8*100 + 0.2*0 = 80
    assert evals[0].distancia_m > 5000
    assert evals[0].score == 80


def test_evaluar_candidatos_ordena_por_score():
    est = _FakeEst()
    candidatos = [
        {
            "id": "ChIJ_lejos",
            "displayName": {"text": "Otra Cosa"},
            "location": {"latitude": 21.0, "longitude": -101.0},
        },
        {
            "id": "ChIJ_cerca",
            "displayName": {"text": "Tortillería La Esperanza"},
            "location": {"latitude": 20.59, "longitude": -100.39},
        },
    ]
    evals = evaluar_candidatos(est, candidatos)
    assert evals[0].place_id == "ChIJ_cerca"
    assert evals[1].place_id == "ChIJ_lejos"


def test_evaluar_candidatos_filtra_invalidos():
    """Candidatos sin id o displayName se ignoran."""
    est = _FakeEst()
    candidatos = [
        {"displayName": {"text": "Sin id"}},
        {"id": "ChIJ_x"},  # sin displayName
        {
            "id": "ChIJ_ok",
            "displayName": {"text": "Tortillería"},
            "location": {"latitude": 20.59, "longitude": -100.39},
        },
    ]
    evals = evaluar_candidatos(est, candidatos)
    assert len(evals) == 1
    assert evals[0].place_id == "ChIJ_ok"
