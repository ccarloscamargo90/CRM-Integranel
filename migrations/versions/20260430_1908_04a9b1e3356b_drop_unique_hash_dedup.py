"""drop_unique_hash_dedup

Revision ID: 04a9b1e3356b
Revises: a1b2c3d4e5f6
Create Date: 2026-04-30 19:08:02.785248

"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '04a9b1e3356b'
down_revision: Union[str, None] = 'a1b2c3d4e5f6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Cambia `hash_dedup` de UNIQUE a índice no-único.

    Razón: el hash colisiona cuando dos establecimientos con CLEE distinto
    comparten nombre genérico ('TORTILLERIA'), CP y coords (o sin coords).
    CLEE es la clave única oficial del DENUE; hash_dedup queda como auxiliar
    para fuzzy dedup entre fuentes (DENUE / Google / Manual)."""
    op.execute("ALTER TABLE establecimientos DROP CONSTRAINT IF EXISTS establecimientos_hash_dedup_key")
    op.execute("CREATE INDEX IF NOT EXISTS idx_est_hash_dedup ON establecimientos(hash_dedup)")


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_est_hash_dedup")
    op.execute(
        "ALTER TABLE establecimientos ADD CONSTRAINT establecimientos_hash_dedup_key UNIQUE (hash_dedup)"
    )
