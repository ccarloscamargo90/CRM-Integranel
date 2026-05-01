"""drop_unique_enriq_place_id

Quita UNIQUE en enriquecimiento_google.place_id. Razón: dos establecimientos
DENUE distintos pueden mapear al mismo lugar físico en Google Maps (matriz +
sucursal en mismo edificio, o duplicado en DENUE). Permitir N:1.

Revision ID: a9b846c36859
Revises: 35e3f2210f11
Create Date: 2026-04-30 23:14:00
"""
from __future__ import annotations

from alembic import op

revision: str = "a9b846c36859"
down_revision: str | None = "35e3f2210f11"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE enriquecimiento_google "
        "DROP CONSTRAINT IF EXISTS enriquecimiento_google_place_id_key"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_enriq_place_id ON enriquecimiento_google(place_id)"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_enriq_place_id")
    op.execute(
        "ALTER TABLE enriquecimiento_google "
        "ADD CONSTRAINT enriquecimiento_google_place_id_key UNIQUE (place_id)"
    )
