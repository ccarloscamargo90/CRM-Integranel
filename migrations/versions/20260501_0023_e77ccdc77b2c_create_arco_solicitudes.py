"""create_arco_solicitudes

Tabla para registrar y rastrear solicitudes ARCO (Acceso, Rectificación,
Cancelación, Oposición) bajo LFPDPPP 2025.

Plazo de respuesta legal: 20 días hábiles desde la recepción.

Revision ID: e77ccdc77b2c
Revises: 9602d1aaf900
Create Date: 2026-05-01 00:23:00
"""
from __future__ import annotations

from alembic import op

revision: str = "e77ccdc77b2c"
down_revision: str | None = "9602d1aaf900"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS arco_solicitudes (
            id                       BIGSERIAL PRIMARY KEY,
            folio                    TEXT UNIQUE NOT NULL,
            tipo                     TEXT NOT NULL CHECK (tipo IN
                ('acceso','rectificacion','cancelacion','oposicion')),
            estatus                  TEXT NOT NULL DEFAULT 'recibida'
                                     CHECK (estatus IN
                ('recibida','en_proceso','respondida','no_procedente','vencida')),

            solicitante_nombre       TEXT NOT NULL,
            solicitante_email        TEXT,
            solicitante_telefono     TEXT,
            solicitante_rfc          TEXT,
            solicitante_razon_social TEXT,
            identificacion_tipo      TEXT,
            identificacion_validada  BOOLEAN NOT NULL DEFAULT false,

            establecimiento_id       BIGINT REFERENCES establecimientos(id) ON DELETE SET NULL,
            descripcion              TEXT NOT NULL,
            datos_solicitados        TEXT[],

            fecha_recepcion          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            fecha_limite_respuesta   DATE NOT NULL,
            fecha_respuesta          TIMESTAMPTZ,
            usuario_responsable_id   BIGINT REFERENCES usuarios(id) ON DELETE SET NULL,

            respuesta                TEXT,
            documentos_anexos        JSONB,
            notas_internas           TEXT
        )
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_arco_estatus ON arco_solicitudes(estatus)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_arco_fecha_limite "
        "ON arco_solicitudes(fecha_limite_respuesta) "
        "WHERE estatus IN ('recibida','en_proceso')"
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS arco_solicitudes")
