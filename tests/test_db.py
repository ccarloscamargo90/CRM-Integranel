"""Tests que requieren Postgres real (vía fixture `db` de conftest)."""

from __future__ import annotations

from sqlalchemy import select, text


def test_postgis_disponible(db):
    """La extensión postgis está habilitada."""
    result = db.execute(text("SELECT PostGIS_Version()")).scalar()
    assert result is not None
    assert "USE_GEOS" in result


def test_pg_trgm_disponible(db):
    """La extensión pg_trgm está habilitada."""
    result = db.execute(
        text("SELECT extversion FROM pg_extension WHERE extname='pg_trgm'")
    ).scalar()
    assert result is not None


def test_columnas_pii_baseline_poblada(db):
    """La migración baseline insertó 21 filas en _columnas_pii."""
    n = db.execute(text("SELECT COUNT(*) FROM _columnas_pii")).scalar()
    assert n == 21, f"Esperaba 21 filas, hay {n}. Re-aplicar migración."


def test_alembic_version_existe(db):
    """La DB tiene una versión registrada en alembic_version."""
    v = db.execute(text("SELECT version_num FROM alembic_version")).scalar()
    assert v is not None
    assert len(v) == 12  # hash de 12 chars


def test_repo_establecimientos_contar(db):
    """El repositorio de establecimientos responde sin errores."""
    from src.core.repos.establecimientos import EstablecimientoRepo

    total = EstablecimientoRepo.contar_total(db)
    assert total >= 0  # tabla vacía o con data, ambas son válidas


def test_compliance_log_helper(db):
    """`registrar_operacion` inserta en compliance_log y devuelve los logs."""
    from sqlalchemy import func

    from src.compliance.lfpdppp import registrar_operacion
    from src.core.models import ComplianceLog

    n_antes = db.execute(select(func.count()).select_from(ComplianceLog)).scalar()

    logs = registrar_operacion(
        session=db,
        tipo_operacion="descarga_denue",
        finalidad="Test smoke",
        base_legal="Fuente de acceso público",
    )
    assert len(logs) == 1
    assert logs[0].id is not None  # flush asignó id

    n_despues = db.execute(select(func.count()).select_from(ComplianceLog)).scalar()
    assert n_despues == n_antes + 1
