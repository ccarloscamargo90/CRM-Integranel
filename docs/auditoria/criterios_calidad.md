# Criterios de calidad — Auditoría DENUE

**Versión:** 1.0
**Fecha:** 2026-04-30
**Aplicable a:** descargas DENUE (Fase 3+) y refresh incrementales.
**Mantenido por:** quien actualiza `src/audit/`.

---

## Filosofía

Cada chequeo emite un **Hallazgo** con tres niveles de severidad:

| Severidad | Acción | Ejemplo |
|---|---|---|
| 🔴 **error** | El registro **se descarta** o requiere intervención manual antes de pasar al pipeline comercial. | `geo.fuera_bbox_mx` — coords claramente erróneas. |
| 🟡 **warning** | El registro **se conserva** pero queda marcado para revisión y no se usa en campañas activas hasta que un humano lo valide. | `completeness.sin_contacto` — no tenemos cómo contactarlo. |
| 🔵 **info** | No es problema, es estadística para diagnóstico. | `completeness.pct_null.telefono` — qué % de la tabla tiene teléfono. |

El runner devuelve un `ReporteAuditoria.aprobado = True` solo si **no hay errors con `total_problemas > 0`**. Warnings no bloquean.

---

## Tabla maestra de chequeos

### Duplicados (`src/audit/duplicates.py`)

| Chequeo | Severidad | Cuándo dispara | Acción |
|---|---|---|---|
| `duplicates.clee` | 🔴 error | Mismo CLEE en dos filas | Bug en upsert DENUE — investigar antes de seguir descargando |
| `duplicates.hash_dedup` | 🔴 error | Mismo `hash_dedup` en dos filas | Bug en función de hash o colisión real |
| `duplicates.fuzzy` | 🟡 warning | Pares con score ≥ 90 en mismo municipio | Fusionar o marcar uno como `pausado` |

### Completitud (`src/audit/completeness.py`)

| Chequeo | Severidad | Cuándo dispara | Acción |
|---|---|---|---|
| `completeness.columnas_criticas` | 🔴 error | NULL en `nombre`, `nombre_norm`, `scian_codigo`, o `hash_dedup` | Descartar registro |
| `completeness.pct_null.{col}` | 🔵 info | Una fila por columna con su % NULL | Solo diagnóstico — no bloquea |
| `completeness.sin_contacto` | 🟡 warning | Sin `telefono`, `whatsapp`, ni `email` | Candidato a enriquecimiento Google Places (Fase 4) |

### Geografía (`src/audit/geo_anomalies.py`)

| Chequeo | Severidad | Cuándo dispara | Acción |
|---|---|---|---|
| `geo.coords_nulas_o_cero` | 🟡 warning | `lat`/`lon` NULL o (0,0) | Conservar, pero excluir de mapas y rutas |
| `geo.fuera_bbox_mx` | 🔴 error | Lat/lon fuera de bbox MX | Descartar — coords claramente inválidas |
| `geo.lat_lon_invertidas` | 🔴 error | Lat parece longitud y viceversa | Corregir manualmente swapeando, después re-validar |
| `geo.geom_vs_lat_lon` | 🟡 warning | `geom` no coincide con (lat, lon) ± 1e-5° | Re-generar `geom` con un UPDATE |

### SCIAN y canales (`src/audit/scian.py`)

| Chequeo | Severidad | Cuándo dispara | Acción |
|---|---|---|---|
| `scian.fuera_objetivo` | 🔴 error | SCIAN no está en los 8 primarios | Descartar — no era parte del scope de Fase 3 |
| `scian.canal_inconsistente` | 🔴 error | El canal natural del SCIAN no aparece en `canales[]` | Reasignar canal correcto |
| `scian.canales_vacio` | 🔴 error | `canales = []` | Asignar al menos el canal natural del SCIAN |
| `scian.distribucion` | 🔵 info | Conteo por SCIAN | Solo diagnóstico |

### Contacto (`src/audit/contacto.py`)

| Chequeo | Severidad | Cuándo dispara | Acción |
|---|---|---|---|
| `contacto.telefono_formato_mx` | 🟡 warning | Tras normalizar, no son 10 dígitos | Conservar, marcar para corrección por vendedor en visita |
| `contacto.email_formato` | 🟡 warning | Email no matchea regex razonable | Igual — corrección manual |
| `contacto.direccion_sospechosa` | 🟡 warning | "domicilio conocido", "s/n", o sin numero_exterior | Vendedor confirma en visita |
| `contacto.anio_alta_denue` | 🟡 warning | < 2005 o > año actual | Probablemente error de captura DENUE — anotar |

---

## Cómo ejecutar

```python
from src.audit import run_all
from src.core.db import SessionLocal

with SessionLocal() as db:
    reporte = run_all(db, universo="establecimientos:Tortillerias:full")
    print(reporte.resumen())

    # Si NO aprueba, listar errors:
    if not reporte.aprobado:
        for h in reporte.errores:
            print(f"  ✗ {h.chequeo}: {h.total_problemas} de {h.total_evaluados}")
            for e in h.ejemplos[:3]:
                print(f"    - {e}")
```

Para subset (universo chico o test):

```python
from src.audit import run_subset

reporte = run_subset(
    db,
    chequeos=["scian.fuera_objetivo", "geo.fuera_bbox_mx", "completeness.columnas_criticas"],
)
```

Para omitir chequeos costosos (`duplicates.fuzzy` es O(n²) por municipio):

```python
reporte = run_all(db, omitir={"duplicates.fuzzy"})
```

---

## Cuándo correr esto

1. **Después de cada descarga DENUE** (Fase 3 — `denue_pipeline.py` lo llama al final de cada batch entidad+SCIAN).
2. **Después de cada enriquecimiento Google Places** (Fase 4 — verifica que match no rompió canales o coords).
3. **Mensualmente** sobre toda la tabla — detecta degradación con el tiempo (errores acumulados).
4. **Antes de exportes masivos** a CSV (Fase 8) — no exportamos data inválida.

---

## Política de descarte vs corrección

Cuando un chequeo `error` dispara, las opciones son:

1. **Descartar el registro** (DELETE FROM establecimientos WHERE id = X). Solo si el registro no tiene actividad humana (no asignado a vendedor, sin interacciones).
2. **Marcar como descartado** (UPDATE estado_pipeline = 'descartado', notas = '<motivo>'). Preferido si el registro tiene historia.
3. **Corregir manualmente** (UPDATE columna específica). Preferido para `geo.lat_lon_invertidas`, `scian.canal_inconsistente`.
4. **Bloquear el batch** y avisar al operador (registrar en `denue_descargas_log` con notas y reintentar después). Preferido para errors masivos (>10% del batch).

Cualquier descarte queda en `compliance_log` con `tipo_operacion = "descarte_calidad"` para trazabilidad LFPDPPP.

---

## Mejoras pendientes (post-Fase 2)

- **Spatial join contra AGEBs** (Fase 5.3) — añadir `geo.fuera_de_ageb_mx` para detectar puntos en océano.
- **Validación cruzada con Google Places** (Fase 4) — `match.score < 60` después de enriquecimiento → registro dudoso.
- **Detección de cadenas mal agrupadas** — `cadena_id` con sucursales que parecen no relacionarse por nombre/dueño.
- **Lista 69-B SAT** (Fase 5.1) — bloquear automáticamente registros con `riesgo_69b = true`.
