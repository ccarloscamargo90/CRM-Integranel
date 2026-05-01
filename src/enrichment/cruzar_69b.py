"""Cruce de establecimientos contra Listado 69-B SAT.

Para cada establecimiento con `rfc` no nulo:
- Si su RFC aparece en `sat_lista_69b` con estatus en {Definitivo, Presunto},
  marca `riesgo_69b = true` y registra `riesgo_69b_fecha` con la fecha de
  publicación DOF más reciente.
- Si solo aparece como Desvirtuado o Sentencia Favorable, queda en
  `riesgo_69b = false` (limpiaron su nombre).

Este cruce se ejecuta tras cada descarga del SAT (mensual) y debe correr
también tras cada descarga DENUE (por si entró un nuevo prospecto que ya
estaba en la lista). Es idempotente: re-correr da los mismos flags.
"""

from __future__ import annotations

from loguru import logger
from sqlalchemy import text
from sqlalchemy.orm import Session

from src.compliance.lfpdppp import registrar_operacion


def cruzar_riesgo_69b(session: Session) -> dict:
    """Actualiza `establecimientos.riesgo_69b` y `riesgo_69b_fecha`.

    Estrategia dual:
    1. Match por **RFC exacto** (alta confianza). Solo aplica si DENUE/manual
       cargaron `rfc` en el establecimiento. La descarga bulk DENUE NO trae RFC,
       así que en práctica este match dispara cuando el operador captura RFC manual.
    2. Match por **razón social uppercased exacta** (confianza media). Fallback
       cuando RFC no está disponible. Posibles falsos positivos si dos empresas
       distintas comparten razón social (raro pero ocurre).

    Returns: {marcados_riesgo, marcados_por_rfc, marcados_por_razon, limpiados,
              total_con_rfc, total_con_razon, total_lista_69b}.
    """
    total_con_rfc = session.execute(
        text(
            "SELECT COUNT(*) FROM establecimientos "
            "WHERE rfc IS NOT NULL AND rfc != ''"
        )
    ).scalar() or 0

    total_con_razon = session.execute(
        text(
            "SELECT COUNT(*) FROM establecimientos "
            "WHERE razon_social IS NOT NULL AND razon_social != ''"
        )
    ).scalar() or 0

    # 1) Match por RFC (alta confianza)
    res_rfc = session.execute(
        text(
            """
            UPDATE establecimientos e
               SET riesgo_69b = true,
                   riesgo_69b_fecha = sub.fecha_max
              FROM (
                SELECT rfc, MAX(fecha_publicacion_dof) AS fecha_max
                  FROM sat_lista_69b
                 WHERE estatus IN ('Definitivo','Presunto')
                 GROUP BY rfc
              ) sub
             WHERE e.rfc = sub.rfc
               AND e.rfc IS NOT NULL AND e.rfc != ''
            """
        )
    )
    marcados_rfc = res_rfc.rowcount or 0

    # 2) Match por razón social uppercased (fallback cuando RFC vacío)
    res_razon = session.execute(
        text(
            """
            UPDATE establecimientos e
               SET riesgo_69b = true,
                   riesgo_69b_fecha = sub.fecha_max
              FROM (
                SELECT UPPER(TRIM(razon_social)) AS razon_norm,
                       MAX(fecha_publicacion_dof) AS fecha_max
                  FROM sat_lista_69b
                 WHERE estatus IN ('Definitivo','Presunto')
                   AND razon_social IS NOT NULL AND razon_social != ''
                 GROUP BY UPPER(TRIM(razon_social))
              ) sub
             WHERE UPPER(TRIM(e.razon_social)) = sub.razon_norm
               AND e.razon_social IS NOT NULL AND e.razon_social != ''
               AND e.riesgo_69b = false   -- no doble-marcar los ya marcados por RFC
            """
        )
    )
    marcados_razon = res_razon.rowcount or 0
    marcados = marcados_rfc + marcados_razon

    # 3) Limpia los que ya no aparecen como riesgo en SAT (cambió a Desvirtuado/Sentencia)
    res_limpia = session.execute(
        text(
            """
            UPDATE establecimientos e
               SET riesgo_69b = false,
                   riesgo_69b_fecha = NULL
             WHERE e.riesgo_69b = true
               AND (e.rfc IS NULL OR e.rfc = '' OR e.rfc NOT IN (
                  SELECT rfc FROM sat_lista_69b
                   WHERE estatus IN ('Definitivo','Presunto')
               ))
               AND (e.razon_social IS NULL OR e.razon_social = ''
                    OR UPPER(TRIM(e.razon_social)) NOT IN (
                  SELECT UPPER(TRIM(razon_social)) FROM sat_lista_69b
                   WHERE estatus IN ('Definitivo','Presunto')
                     AND razon_social IS NOT NULL
               ))
            """
        )
    )
    limpiados = res_limpia.rowcount or 0

    session.commit()

    # Compliance log
    registrar_operacion(
        session=session,
        tipo_operacion="cruce_sat_69b",
        finalidad=(
            "Marcar prospectos en Lista 69-B SAT para excluirlos de campañas activas. "
            "Estatus considerados riesgo: Definitivo, Presunto. "
            "Estatus considerados limpios: Desvirtuado, Sentencia Favorable."
        ),
        base_legal="Información pública oficial SAT (Art. 69-B CFF, publicada en DOF)",
        columnas_tocadas=["riesgo_69b", "riesgo_69b_fecha"],
        notas=f"marcados={marcados} limpiados={limpiados} total_con_rfc={total_con_rfc}",
    )
    session.commit()

    logger.info(
        "Cruce 69-B: {m} marcados riesgo, {l} limpiados, {t} con RFC",
        m=marcados, l=limpiados, t=total_con_rfc,
    )

    return {
        "marcados_riesgo": marcados,
        "marcados_por_rfc": marcados_rfc,
        "marcados_por_razon": marcados_razon,
        "limpiados": limpiados,
        "total_con_rfc": total_con_rfc,
        "total_con_razon": total_con_razon,
        "total_lista_69b": session.execute(
            text("SELECT COUNT(*) FROM sat_lista_69b")
        ).scalar() or 0,
    }
