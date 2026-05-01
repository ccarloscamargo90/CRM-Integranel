"""Tests del parser CSV → dict de Establecimiento."""

from __future__ import annotations

import pytest

from src.ingestion.denue_csv_parser import (
    CsvParseError,
    _anio_de_fecha_alta,
    csv_row_to_establecimiento_dict,
)


def _row_minimo(**overrides) -> dict[str, str]:
    base = {
        "clee": "23005311830000010000000000U7",
        "nom_estab": "TORTILLERIA TEST",
        "raz_social": "",
        "codigo_act": "311830",
        "nombre_act": "Elaboración de tortillas de maíz",
        "per_ocu": "0 a 5 personas",
        "cve_ent": "23",
        "entidad": "Quintana Roo",
        "cve_mun": "005",
        "cod_postal": "77000",
        "latitud": "19.0",
        "longitud": "-88.5",
        "fecha_alta": "2018-05",
        "telefono": "",
    }
    base.update(overrides)
    return base


def test_parser_csv_basico():
    row = _row_minimo()
    d = csv_row_to_establecimiento_dict(row)
    assert d["clee"] == "23005311830000010000000000U7"
    assert d["nombre"] == "TORTILLERIA TEST"
    assert d["scian_codigo"] == "311830"
    assert d["estado_codigo"] == "23"
    assert d["municipio_codigo"] == "005"
    assert d["latitud"] == 19.0
    assert d["longitud"] == -88.5
    assert d["empleados_est"] == 3
    assert d["fuentes"] == ["DENUE_CSV"]


def test_parser_csv_calcula_anio_alta():
    row = _row_minimo(fecha_alta="2010-07")
    d = csv_row_to_establecimiento_dict(row)
    assert d["anio_alta_denue"] == 2010


def test_parser_csv_falla_sin_clee():
    row = _row_minimo(clee="")
    with pytest.raises(CsvParseError, match="clee"):
        csv_row_to_establecimiento_dict(row)


def test_parser_csv_falla_sin_nombre_ni_razon_social():
    row = _row_minimo(nom_estab="", raz_social="")
    with pytest.raises(CsvParseError, match="nom_estab"):
        csv_row_to_establecimiento_dict(row)


def test_parser_csv_usa_razon_social_si_nom_estab_vacio():
    row = _row_minimo(nom_estab="", raz_social="TORTILLERIAS SA DE CV")
    d = csv_row_to_establecimiento_dict(row)
    assert d["nombre"] == "TORTILLERIAS SA DE CV"


def test_parser_csv_telefono_se_propaga():
    row = _row_minimo(telefono="9831234567")
    d = csv_row_to_establecimiento_dict(row)
    assert d["telefono"] == "9831234567"


def test_parser_csv_lat_lon_invalidos_devuelve_none():
    row = _row_minimo(latitud="abc", longitud="")
    d = csv_row_to_establecimiento_dict(row)
    assert d["latitud"] is None
    assert d["longitud"] is None


def test_parser_csv_canales_se_calcula_de_scian():
    row = _row_minimo(codigo_act="311110")
    d = csv_row_to_establecimiento_dict(row)
    assert d["canales"] == ["AlimentoBalanceado"]


def test_parser_csv_volumen_y_tipo():
    row = _row_minimo(per_ocu="6 a 10 personas")  # 8 empleados
    d = csv_row_to_establecimiento_dict(row)
    assert d["empleados_est"] == 8
    # 8 × 1.8 = 14.4 (tortilleria_tradicional)
    assert d["volumen_estimado_ton_mes"] == 14.4


def test_anio_de_fecha_alta_acepta_formatos():
    assert _anio_de_fecha_alta("2010-07") == 2010
    assert _anio_de_fecha_alta("2024-11") == 2024
    assert _anio_de_fecha_alta(None) is None
    assert _anio_de_fecha_alta("") is None
    assert _anio_de_fecha_alta("texto") is None
