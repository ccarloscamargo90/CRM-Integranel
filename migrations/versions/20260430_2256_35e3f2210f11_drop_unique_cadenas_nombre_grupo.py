"""drop_unique_cadenas_nombre_grupo

Revision ID: 35e3f2210f11
Revises: 04a9b1e3356b
Create Date: 2026-04-30 22:56:13.141803

"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '35e3f2210f11'
down_revision: Union[str, None] = '04a9b1e3356b'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Quita UNIQUE de cadenas.nombre_grupo (legible). Mantiene UNIQUE en
    nombre_grupo_norm que es la clave estable. Razón: dos empresas distintas
    pueden tener marcas comerciales con el mismo nombre legible (ej. dos
    razones sociales distintas operan 'Tortillería Michoacán' en estados
    distintos)."""
    op.execute("ALTER TABLE cadenas DROP CONSTRAINT IF EXISTS cadenas_nombre_grupo_key")


def downgrade() -> None:
    op.execute("ALTER TABLE cadenas ADD CONSTRAINT cadenas_nombre_grupo_key UNIQUE (nombre_grupo)")
