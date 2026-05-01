"""Modelos Pydantic para reportes de auditoría.

Cada chequeo devuelve un `Hallazgo`. El runner agrega los hallazgos en un
`ReporteAuditoria` que se puede serializar a JSON, almacenar y visualizar.

Convenciones:
- `severidad="error"` → registro debe descartarse o requiere intervención manual.
- `severidad="warning"` → registro se conserva pero se marca para revisión.
- `severidad="info"` → no es problema, es estadística (% de campos llenos, etc.).
"""

from __future__ import annotations

import datetime as dt
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

Severidad = Literal["error", "warning", "info"]


class Hallazgo(BaseModel):
    """Un chequeo aplicado sobre un universo y su resultado."""

    model_config = ConfigDict(frozen=True)

    chequeo: str = Field(..., description="Nombre del chequeo, ej. 'duplicates.clee'")
    severidad: Severidad
    total_evaluados: int = Field(..., ge=0)
    total_problemas: int = Field(..., ge=0)
    detalle: str | None = None
    ejemplos: list[dict[str, Any]] = Field(
        default_factory=list,
        description="Hasta 10 ejemplos para revisión manual (sin PII expuesta)",
    )

    @property
    def pct_problemas(self) -> float:
        if self.total_evaluados == 0:
            return 0.0
        return round(100.0 * self.total_problemas / self.total_evaluados, 2)

    @property
    def aprobado(self) -> bool:
        """True si no hay problemas o son sólo `info`."""
        return self.severidad == "info" or self.total_problemas == 0


class ReporteAuditoria(BaseModel):
    """Conjunto de hallazgos producidos por una corrida del runner."""

    fecha: dt.datetime = Field(default_factory=lambda: dt.datetime.now(dt.UTC))
    universo: str = Field(
        ...,
        description="Filtro aplicado, ej. 'establecimientos:Tortillerias:cve_entidad=09'",
    )
    total_registros: int = Field(..., ge=0)
    hallazgos: list[Hallazgo]

    @property
    def errores(self) -> list[Hallazgo]:
        return [h for h in self.hallazgos if h.severidad == "error" and h.total_problemas > 0]

    @property
    def warnings(self) -> list[Hallazgo]:
        return [h for h in self.hallazgos if h.severidad == "warning" and h.total_problemas > 0]

    @property
    def aprobado(self) -> bool:
        return len(self.errores) == 0

    def resumen(self) -> dict[str, Any]:
        """Resumen compacto para logs y dashboards."""
        return {
            "fecha": self.fecha.isoformat(),
            "universo": self.universo,
            "total_registros": self.total_registros,
            "n_hallazgos": len(self.hallazgos),
            "n_errores": len(self.errores),
            "n_warnings": len(self.warnings),
            "aprobado": self.aprobado,
        }
