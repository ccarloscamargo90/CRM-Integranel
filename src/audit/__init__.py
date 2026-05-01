"""audit — auditoría automática de calidad de datos.

Módulos:
- `models.py`        Pydantic models para `Hallazgo` y `ReporteAuditoria`
- `duplicates.py`    duplicados CLEE, hash_dedup, fuzzy nombre+dirección
- `completeness.py`  columnas críticas, % NULL, registros sin contacto
- `geo_anomalies.py` coords nulas, fuera bbox MX, lat/lon invertidas, geom desync
- `scian.py`         SCIAN objetivo, consistencia canal, canales vacíos
- `contacto.py`      teléfono MX, email, direcciones sospechosas, anio_alta razonable
- `runner.py`        orquestador `run_all()` que devuelve `ReporteAuditoria`

Cada chequeo es una función pura `(Session) -> Hallazgo`. Devuelve estructura
con severidad (`error` / `warning` / `info`), conteo y ejemplos para revisión.

El runner es composable: `run_all()` corre todo, `run_subset(["..."])` corre lo
que pidas. Ver `docs/auditoria/criterios_calidad.md` para reglas de severidad.
"""

from src.audit.models import Hallazgo, ReporteAuditoria, Severidad
from src.audit.runner import run_all, run_subset

__all__ = ["Hallazgo", "ReporteAuditoria", "Severidad", "run_all", "run_subset"]
