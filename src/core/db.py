"""Acceso a base de datos — engine SQLAlchemy + sesión + dependencia FastAPI.

Reglas:
- `engine` y `SessionLocal` se crean una sola vez al importar el módulo (singleton).
- Para FastAPI: usar `Depends(get_db)`.
- Para scripts CLI / Jupyter: usar `with SessionLocal() as session:`.
- NUNCA mantener una sesión viva entre requests; siempre cerrar.
"""

from __future__ import annotations

from collections.abc import Generator

from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from .config import get_settings


class Base(DeclarativeBase):
    """Base declarativa para todos los modelos ORM (estilo SQLAlchemy 2.0).

    Cualquier modelo en `src/core/models.py` hereda de esta clase.
    Los modelos NO definen `__tablename__` automático — lo declaran explícito
    para que coincida con el schema SQL.
    """


def _make_engine() -> Engine:
    settings = get_settings()
    return create_engine(
        settings.DATABASE_URL,
        echo=settings.DATABASE_ECHO,
        pool_pre_ping=True,  # valida conexión antes de usarla (auto-reconnect)
        pool_size=5,
        max_overflow=10,
        future=True,
    )


# Singletons del módulo
engine: Engine = _make_engine()
SessionLocal: sessionmaker[Session] = sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=engine,
    expire_on_commit=False,  # los objetos siguen accesibles tras commit
)


def get_db() -> Generator[Session, None, None]:
    """Dependencia FastAPI — abre sesión por request, la cierra al terminar.

    Uso:
        @app.get("/...")
        def endpoint(db: Session = Depends(get_db)):
            ...
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
