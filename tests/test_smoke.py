"""Smoke tests — verifican que el scaffold compila e importa.

Estos tests NO requieren Postgres. Si fallan, hay un error de sintaxis o de
imports en el scaffold y todo lo demás también va a fallar.
"""

from __future__ import annotations


def test_paquete_se_importa():
    import src

    assert src.__version__ == "0.1.0"


def test_subpaquetes_existen():
    """Cada subpaquete debe importarse sin errores."""
    from src import api, audit, compliance, core, enrichment, ingestion

    assert all([api, audit, compliance, core, enrichment, ingestion])


def test_python_version():
    """Confirma que corremos en Python ≥ 3.11."""
    import sys

    assert sys.version_info >= (3, 11), f"Se requiere 3.11+, hay {sys.version_info}"


def test_models_se_importan():
    """Las 14 clases ORM se cargan sin errores."""
    from src.core.models import (
        Ageb,
        Cadena,
        ColumnaPII,
        ComplianceLog,
        DenueDescargaLog,
        EnriquecimientoGoogle,
        Establecimiento,
        GooglePlacesLog,
        IndicadorGeografico,
        Interaccion,
        PipelineEtapaHistorial,
        SatLista69B,
        Usuario,
        Vendedor,
    )

    modelos = [
        Ageb, Cadena, ColumnaPII, ComplianceLog, DenueDescargaLog,
        Establecimiento, EnriquecimientoGoogle, GooglePlacesLog,
        IndicadorGeografico, Interaccion, PipelineEtapaHistorial,
        SatLista69B, Usuario, Vendedor,
    ]
    nombres = {m.__tablename__ for m in modelos}
    esperados = {
        "agebs", "cadenas", "_columnas_pii", "compliance_log", "denue_descargas_log",
        "establecimientos", "enriquecimiento_google", "google_places_log",
        "indicadores_geograficos", "interacciones", "pipeline_etapas_historial",
        "sat_lista_69b", "usuarios", "vendedores",
    }
    assert nombres == esperados, f"Faltantes: {esperados - nombres}, sobrantes: {nombres - esperados}"


def test_settings_carga_env():
    """Pydantic Settings lee .env (si existe) sin explotar."""
    from src.core.config import get_settings

    settings = get_settings()
    assert settings.APP_NAME == "CRM-Granos-MX"
    assert settings.ENVIRONMENT in ("development", "staging", "production")
    assert settings.DATABASE_URL  # no vacío
