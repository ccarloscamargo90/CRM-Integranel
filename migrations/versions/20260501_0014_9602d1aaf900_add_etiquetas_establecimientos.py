"""add_etiquetas_establecimientos

Añade columna `etiquetas TEXT[]` para tags externos:
- CONAFAB (socio del Consejo Nacional Fabricantes Alimento Balanceado)
- PECUARIO_GRANDE (productor pecuario grande según fuentes públicas)
- CANAMI (cuando se identifique fuente)
- etc.

Se usa para enriquecer scoring (F6): un establecimiento etiquetado como
CONAFAB es un cliente verificado y suma puntos al score.

Revision ID: 9602d1aaf900
Revises: 4c187a972d6e
Create Date: 2026-05-01 00:14:00
"""
from __future__ import annotations

from alembic import op

revision: str = "9602d1aaf900"
down_revision: str | None = "4c187a972d6e"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE establecimientos ADD COLUMN IF NOT EXISTS "
        "etiquetas TEXT[] NOT NULL DEFAULT ARRAY[]::TEXT[]"
    )
    op.execute("CREATE INDEX IF NOT EXISTS idx_est_etiquetas ON establecimientos USING gin(etiquetas)")


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_est_etiquetas")
    op.execute("ALTER TABLE establecimientos DROP COLUMN IF EXISTS etiquetas")
