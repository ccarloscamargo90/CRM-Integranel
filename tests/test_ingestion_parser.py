"""Tests del parser DENUE → dict de Establecimiento."""

from __future__ import annotations

import pytest

from src.ingestion.denue_models import EstablecimientoDenueRaw
from src.ingestion.denue_parser import ParseError, to_establecimiento_dict


def _raw_minimo(**overrides) -> EstablecimientoDenueRaw:
    """Construye un raw mínimo válido (CLEE + Nombre + Latitud + Longitud)."""
    base = {
        "CLEE": "23005311830000010000000000U7",  # entidad 23, mun 005, SCIAN 311830
        "Nombre": "Tortillería La Esperanza",
        "Razon_social": None,
        "Clase_actividad": "Elaboración de tortillas de maíz",
        "Estrato": "0 a 5 personas",
        "Tipo_vialidad": "CALLE",
        "Calle": "Reforma",
        "Num_Exterior": "100",
        "Colonia": "Centro",
        "CP": "77000",
        "Telefono": "9831234567",
        "Latitud": "19.0",
        "Longitud": "-88.5",
        "Tipo": "Fijo",
    }
    base.update(overrides)
    return EstablecimientoDenueRaw.model_validate(base)


def test_parser_mapea_campos_basicos():
    raw = _raw_minimo()
    d = to_establecimiento_dict(raw)
    assert d["clee"] == "23005311830000010000000000U7"
    assert d["nombre"] == "Tortillería La Esperanza"
    assert d["nombre_norm"] == "tortilleria la esperanza"
    assert d["scian_codigo"] == "311830"
    assert d["estado_codigo"] == "23"
    assert d["municipio_codigo"] == "005"
    assert d["latitud"] == 19.0
    assert d["longitud"] == -88.5


def test_parser_calcula_canales():
    raw = _raw_minimo()
    d = to_establecimiento_dict(raw)
    assert d["canales"] == ["Tortillerias"]


def test_parser_calcula_tipo_establecimiento():
    raw = _raw_minimo(Nombre="Molino Nixtamal Don Pepe")
    d = to_establecimiento_dict(raw)
    assert d["tipo_establecimiento"] == "molino_nixtamal"


def test_parser_calcula_volumen():
    raw = _raw_minimo(Estrato="6 a 10 personas")  # 8 empleados × 1.8 = 14.4
    d = to_establecimiento_dict(raw)
    assert d["empleados_est"] == 8
    assert d["volumen_estimado_ton_mes"] == 14.4


def test_parser_arma_direccion():
    raw = _raw_minimo()
    d = to_establecimiento_dict(raw)
    assert "Reforma" in d["direccion"]
    assert "100" in d["direccion"]
    assert "Centro" in d["direccion"]


def test_parser_calcula_hash_dedup():
    raw = _raw_minimo()
    d = to_establecimiento_dict(raw)
    assert isinstance(d["hash_dedup"], str)
    assert len(d["hash_dedup"]) == 40


def test_parser_marca_fuente_denue():
    raw = _raw_minimo()
    d = to_establecimiento_dict(raw)
    assert d["fuentes"] == ["DENUE_API"]


def test_parser_falla_sin_clee():
    raw = EstablecimientoDenueRaw(CLEE="", Nombre="X")
    with pytest.raises(ParseError, match="CLEE"):
        to_establecimiento_dict(raw)


def test_parser_falla_sin_nombre():
    raw = EstablecimientoDenueRaw(CLEE="23005311830000010000000000U7", Nombre=None, Razon_social=None)
    with pytest.raises(ParseError, match="Nombre"):
        to_establecimiento_dict(raw)


def test_parser_usa_razon_social_si_nombre_vacio():
    raw = _raw_minimo(Nombre=None, Razon_social="Tortillerías SA de CV")
    d = to_establecimiento_dict(raw)
    assert d["nombre"] == "Tortillerías SA de CV"


def test_parser_lat_lon_invalidos_devuelve_none():
    raw = _raw_minimo(Latitud="abc", Longitud="xyz")
    d = to_establecimiento_dict(raw)
    assert d["latitud"] is None
    assert d["longitud"] is None
