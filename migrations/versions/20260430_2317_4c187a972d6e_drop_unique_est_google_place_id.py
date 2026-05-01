"""drop_unique_est_google_place_id

Quita UNIQUE en establecimientos.google_place_id. Misma razón que el
constraint en enriquecimiento_google: dos DENUE distintos pueden mapear
al mismo lugar físico de Google Maps.

Revision ID: 4c187a972d6e
Revises: a9b846c36859
Create Date: 2026-04-30 23:17:00
"""
from __future__ import annotations

from alembic import op

revision: str = "4c187a972d6e"
down_revision: str | None = "a9b846c36859"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE establecimientos "
        "DROP CONSTRAINT IF EXISTS establecimientos_google_place_id_key"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_est_google_place_id "
        "ON establecimientos(google_place_id) WHERE google_place_id IS NOT NULL"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_est_google_place_id")
    op.execute(
        "ALTER TABLE establecimientos "
        "ADD CONSTRAINT establecimientos_google_place_id_key UNIQUE (google_place_id)"
    )
