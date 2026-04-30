"""baseline — schema inicial CRM-Granos-MX

Aplica el DDL completo descrito en db/schema.sql:
- Extensiones postgis y pg_trgm
- Catálogo PII y bitácora compliance_log
- Tablas core (vendedores, usuarios, cadenas, establecimientos)
- Enriquecimiento Google y bitácora de interacciones
- Histórico de cambios de etapa (deuda técnica del legacy)
- Logs de fuentes externas (denue, google places)
- SAT 69-B, AGEBs e indicadores geográficos
- Vistas agregadas (resumen, pipeline_vendedor, cobertura, canales)
- Catálogo inicial _columnas_pii con todas las columnas PII conocidas

Revision ID: a1b2c3d4e5f6
Revises:
Create Date: 2026-04-30 15:00
"""
from __future__ import annotations

from pathlib import Path
from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "a1b2c3d4e5f6"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# Catálogo inicial de columnas PII — defensa LFPDPPP.
# Cada columna nueva con datos personales se añade aquí en su propia migración.
COLUMNAS_PII_BASELINE = [
    # tabla, columna, base_legal, finalidad, retencion_meses, notas
    ("vendedores", "nombre", "Relación laboral con Intergranel", "Identificación del vendedor responsable", 60, "PII de empleado"),
    ("vendedores", "email", "Relación laboral con Intergranel", "Comunicación operativa interna", 60, ""),
    ("vendedores", "telefono", "Relación laboral con Intergranel", "Comunicación operativa interna", 60, ""),
    ("usuarios", "nombre", "Relación laboral con Intergranel", "Identificación de usuarios del sistema", 60, ""),
    ("usuarios", "email", "Relación laboral con Intergranel", "Recuperación de cuenta y notificaciones", 60, ""),
    ("cadenas", "contacto_central_nombre", "Interés legítimo comercial B2B", "Contacto comercial central de cadena", 36, "Puede ser PF representante"),
    ("cadenas", "contacto_central_tel", "Interés legítimo comercial B2B", "Contacto comercial central de cadena", 36, ""),
    ("cadenas", "contacto_central_email", "Interés legítimo comercial B2B", "Contacto comercial central de cadena", 36, ""),
    ("establecimientos", "nombre", "Fuente de acceso público (DENUE)", "Identificación del establecimiento prospecto", 60, "Puede contener nombre de PF si el establecimiento es PF con actividad empresarial"),
    ("establecimientos", "razon_social", "Fuente de acceso público (DENUE) + Interés legítimo B2B", "Identificación legal del prospecto", 60, "Puede contener nombre de PF"),
    ("establecimientos", "rfc", "Fuente de acceso público (DENUE)", "Identificación fiscal y cruce con Listado 69-B SAT", 60, "RFC de PF es PII"),
    ("establecimientos", "telefono", "Fuente de acceso público (DENUE) + Interés legítimo B2B", "Contacto comercial inicial", 36, ""),
    ("establecimientos", "whatsapp", "Interés legítimo B2B con consentimiento implícito por uso comercial", "Contacto comercial", 36, "Inferido de número celular MX"),
    ("establecimientos", "email", "Fuente de acceso público (DENUE) + Interés legítimo B2B", "Contacto comercial inicial", 36, ""),
    ("establecimientos", "contacto_nombre", "Consentimiento del prospecto al iniciar relación comercial", "Trato personalizado en visitas y seguimiento", 36, "Capturado por vendedor en campo"),
    ("establecimientos", "contacto_telefono", "Consentimiento del prospecto al iniciar relación comercial", "Contacto directo del decisor", 36, ""),
    ("establecimientos", "contacto_email", "Consentimiento del prospecto al iniciar relación comercial", "Contacto directo del decisor", 36, ""),
    ("enriquecimiento_google", "google_phone", "Fuente pública (Google Places API oficial)", "Contacto comercial verificado", 12, "Refresh trimestral"),
    ("interacciones", "contacto_persona", "Consentimiento implícito por interacción comercial activa", "Trazabilidad de la conversación comercial", 36, "Persona física con la que se habló"),
    ("sat_lista_69b", "rfc", "Información pública oficial publicada en DOF", "Cruce de riesgo fiscal y exclusión de campañas activas", 24, "Lista pública del SAT, art 69-B CFF"),
    ("sat_lista_69b", "razon_social", "Información pública oficial publicada en DOF", "Cruce de riesgo fiscal", 24, ""),
]


def upgrade() -> None:
    # 1) Aplica el DDL del schema.sql.
    schema_path = Path(__file__).resolve().parents[2] / "db" / "schema.sql"
    if not schema_path.exists():
        raise FileNotFoundError(f"No se encontró schema.sql en {schema_path}")
    sql = schema_path.read_text(encoding="utf-8")
    # Postgres soporta múltiples statements en una sola ejecución.
    op.execute(sql)

    # 2) Llena el catálogo inicial de PII.
    for tabla, columna, base_legal, finalidad, retencion, notas in COLUMNAS_PII_BASELINE:
        # Sanitización básica para evitar problemas con apóstrofes.
        def esc(s: str) -> str:
            return s.replace("'", "''")

        op.execute(
            f"""
            INSERT INTO _columnas_pii (tabla, columna, base_legal, finalidad, retencion_meses, notas)
            VALUES ('{esc(tabla)}', '{esc(columna)}', '{esc(base_legal)}', '{esc(finalidad)}', {retencion}, '{esc(notas)}')
            ON CONFLICT (tabla, columna) DO NOTHING;
            """
        )


def downgrade() -> None:
    # Orden inverso (respeta FKs).
    statements = [
        "DROP VIEW IF EXISTS vw_canales_resumen CASCADE;",
        "DROP VIEW IF EXISTS vw_cobertura_municipio CASCADE;",
        "DROP VIEW IF EXISTS vw_pipeline_vendedor CASCADE;",
        "DROP VIEW IF EXISTS vw_establecimientos_resumen CASCADE;",
        "DROP TABLE IF EXISTS compliance_log CASCADE;",
        "DROP TABLE IF EXISTS indicadores_geograficos CASCADE;",
        "DROP TABLE IF EXISTS agebs CASCADE;",
        "DROP TABLE IF EXISTS sat_lista_69b CASCADE;",
        "DROP TABLE IF EXISTS google_places_log CASCADE;",
        "DROP TABLE IF EXISTS denue_descargas_log CASCADE;",
        "DROP TABLE IF EXISTS pipeline_etapas_historial CASCADE;",
        "DROP TABLE IF EXISTS interacciones CASCADE;",
        "DROP TABLE IF EXISTS enriquecimiento_google CASCADE;",
        "DROP TABLE IF EXISTS establecimientos CASCADE;",
        "DROP TABLE IF EXISTS cadenas CASCADE;",
        "DROP TABLE IF EXISTS usuarios CASCADE;",
        "DROP TABLE IF EXISTS vendedores CASCADE;",
        "DROP TABLE IF EXISTS _columnas_pii CASCADE;",
        "DROP EXTENSION IF EXISTS pg_trgm;",
        "DROP EXTENSION IF EXISTS postgis;",
    ]
    for s in statements:
        op.execute(s)
