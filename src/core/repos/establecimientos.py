"""Repositorio de Establecimientos."""

from __future__ import annotations

from collections.abc import Sequence

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from src.core.models import Establecimiento


class EstablecimientoRepo:
    """Acceso a la tabla `establecimientos`."""

    @staticmethod
    def get_by_id(session: Session, est_id: int) -> Establecimiento | None:
        return session.get(Establecimiento, est_id)

    @staticmethod
    def get_by_clee(session: Session, clee: str) -> Establecimiento | None:
        stmt = select(Establecimiento).where(Establecimiento.clee == clee)
        return session.execute(stmt).scalar_one_or_none()

    @staticmethod
    def get_by_hash(session: Session, hash_dedup: str) -> Establecimiento | None:
        stmt = select(Establecimiento).where(Establecimiento.hash_dedup == hash_dedup)
        return session.execute(stmt).scalar_one_or_none()

    @staticmethod
    def listar_por_canal(
        session: Session, canal: str, *, limit: int = 100, offset: int = 0
    ) -> Sequence[Establecimiento]:
        """Devuelve establecimientos que tienen `canal` en su array `canales`."""
        stmt = (
            select(Establecimiento)
            .where(Establecimiento.canales.any(canal))
            .limit(limit)
            .offset(offset)
        )
        return session.execute(stmt).scalars().all()

    @staticmethod
    def contar_total(session: Session) -> int:
        stmt = select(func.count()).select_from(Establecimiento)
        return session.execute(stmt).scalar_one()

    @staticmethod
    def contar_por_estado(session: Session) -> dict[str, int]:
        """{cve_entidad: total} para vista coroplética."""
        stmt = (
            select(Establecimiento.estado_codigo, func.count(Establecimiento.id))
            .where(Establecimiento.estado_codigo.is_not(None))
            .group_by(Establecimiento.estado_codigo)
        )
        return {row[0]: row[1] for row in session.execute(stmt).all()}

    @staticmethod
    def crear(session: Session, **kwargs) -> Establecimiento:
        """Crea un establecimiento sin commitear. Caller hace commit."""
        est = Establecimiento(**kwargs)
        session.add(est)
        session.flush()  # asigna id sin commit
        return est
