"""Repositorio de Vendedores."""

from __future__ import annotations

from collections.abc import Sequence

from sqlalchemy import select
from sqlalchemy.orm import Session

from src.core.models import Vendedor


class VendedorRepo:
    @staticmethod
    def get_by_id(session: Session, vid: int) -> Vendedor | None:
        return session.get(Vendedor, vid)

    @staticmethod
    def get_by_codigo(session: Session, codigo: str) -> Vendedor | None:
        stmt = select(Vendedor).where(Vendedor.codigo == codigo)
        return session.execute(stmt).scalar_one_or_none()

    @staticmethod
    def listar_activos(session: Session) -> Sequence[Vendedor]:
        stmt = select(Vendedor).where(Vendedor.activo.is_(True)).order_by(Vendedor.nombre)
        return session.execute(stmt).scalars().all()

    @staticmethod
    def crear(session: Session, **kwargs) -> Vendedor:
        v = Vendedor(**kwargs)
        session.add(v)
        session.flush()
        return v
