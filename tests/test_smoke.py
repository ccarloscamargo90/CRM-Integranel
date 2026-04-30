"""Smoke tests — sólo verifican que el scaffold compila e importa.

Cuando empecemos Fase 1, aquí migramos a tests con fixtures de Postgres.
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
    """Confirma que corremos en Python ≥ 3.11 como pide pyproject."""
    import sys

    assert sys.version_info >= (3, 11), f"Se requiere 3.11+, hay {sys.version_info}"
