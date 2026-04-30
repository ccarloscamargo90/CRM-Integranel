"""Configuración global de tests — fixtures de Postgres y sesiones aisladas.

Estrategia: **transaction-per-test**. Cada test arranca con un BEGIN y termina
con un ROLLBACK. La DB queda intacta entre tests, sin necesidad de re-aplicar
migraciones cada vez. Mucho más rápido que crear DB efímera por test.

Requisito: la DB de tests (`crm_granos_mx_test`) debe existir y tener el schema
aplicado. Se crea una vez con:

    createdb crm_granos_mx_test
    psql crm_granos_mx_test -c "CREATE EXTENSION postgis;"
    psql crm_granos_mx_test -c "CREATE EXTENSION pg_trgm;"
    DATABASE_URL=postgresql+psycopg://carlosacamargo@localhost:5432/crm_granos_mx_test \
        python -m alembic upgrade head

En CI, el job de GitHub Actions ejecuta esto automáticamente al levantar el
servicio Postgres con PostGIS.
"""

from __future__ import annotations

import os
from collections.abc import Generator

import pytest
from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker


def _get_test_database_url() -> str:
    """Pieces apart the production DATABASE_URL and remaps to `..._test` DB."""
    prod_url = os.getenv("DATABASE_URL", "")
    if not prod_url:
        # Fallback útil para correr local sin .env cargado
        return "postgresql+psycopg://carlosacamargo@localhost:5432/crm_granos_mx_test"
    if "_test" in prod_url:
        return prod_url
    # Reemplaza el último segmento (la DB) con `..._test`
    if "/" in prod_url:
        head, db = prod_url.rsplit("/", 1)
        return f"{head}/{db.split('?')[0]}_test"
    return prod_url


@pytest.fixture(scope="session")
def engine() -> Generator[Engine, None, None]:
    """Engine global compartido entre tests de la sesión."""
    url = _get_test_database_url()
    eng = create_engine(url, pool_pre_ping=True, future=True)
    yield eng
    eng.dispose()


@pytest.fixture(scope="function")
def db(engine: Engine) -> Generator[Session, None, None]:
    """Sesión por test. Nested transaction → rollback al terminar."""
    connection = engine.connect()
    transaction = connection.begin()
    session_factory = sessionmaker(bind=connection, autoflush=False, expire_on_commit=False)
    session = session_factory()

    try:
        yield session
    finally:
        session.close()
        transaction.rollback()
        connection.close()
