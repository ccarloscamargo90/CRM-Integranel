"""Modelos Pydantic para respuestas de la API DENUE.

Estos modelos validan la forma de los JSON que devuelve INEGI. Si INEGI
cambia el contrato (raro), Pydantic explota con error legible en lugar de
producir registros corruptos.

Referencia oficial: https://www.inegi.org.mx/app/api/denue/v1/
URL base: https://www.inegi.org.mx/app/api/denue/v1/consulta/
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator


class CuantificarItem(BaseModel):
    """Una fila del endpoint Cuantificar — conteo por (SCIAN, entidad)."""

    AE: str = Field(..., description="Actividad Económica (SCIAN)")
    AG: str = Field(..., description="Área Geográfica (cve_entidad)")
    Total: str = Field(..., description="Conteo como string — Pydantic convierte")

    @property
    def total_int(self) -> int:
        return int(self.Total)


class EstablecimientoDenueRaw(BaseModel):
    """Una fila del endpoint BuscarEntidad o Nombre — un establecimiento.

    Campos en CamelCase porque DENUE los devuelve así. NO renombramos —
    el parser (`denue_parser.py`) hace el mapping a nuestro schema.
    """

    model_config = ConfigDict(extra="ignore")  # ignora campos nuevos que añada INEGI

    CLEE: str
    Id: str | None = None
    Nombre: str | None = None
    Razon_social: str | None = None
    Clase_actividad: str | None = None
    Estrato: str | None = None
    Tipo_vialidad: str | None = None
    Calle: str | None = None
    Num_Exterior: str | None = None
    Num_Interior: str | None = None
    Colonia: str | None = None
    CP: str | None = None
    Ubicacion: str | None = None
    Telefono: str | None = None
    Correo_e: str | None = None
    Sitio_internet: str | None = None
    Tipo: str | None = None  # 'Fijo' | 'Semifijo'
    Longitud: str | None = None
    Latitud: str | None = None

    # Campos opcionales menos comunes (algunos solo aparecen en Ficha):
    tipo_corredor_industrial: str | None = None
    nom_corredor_industrial: str | None = None
    numero_local: str | None = None

    @field_validator("Latitud", "Longitud", mode="before")
    @classmethod
    def _coerce_str(cls, v: Any) -> str | None:
        """DENUE a veces devuelve floats, a veces strings. Normalizamos a str."""
        if v is None or v == "":
            return None
        return str(v)

    @property
    def lat_float(self) -> float | None:
        try:
            return float(self.Latitud) if self.Latitud else None
        except (TypeError, ValueError):
            return None

    @property
    def lon_float(self) -> float | None:
        try:
            return float(self.Longitud) if self.Longitud else None
        except (TypeError, ValueError):
            return None

    @property
    def cve_entidad(self) -> str | None:
        """Primeros 2 chars del CLEE = código de entidad INEGI."""
        if not self.CLEE or len(self.CLEE) < 2:
            return None
        return self.CLEE[:2]

    @property
    def cve_municipio(self) -> str | None:
        """Chars 2-5 del CLEE = código de municipio dentro de la entidad."""
        if not self.CLEE or len(self.CLEE) < 5:
            return None
        return self.CLEE[2:5]


class DenueErrorRespuesta(BaseModel):
    """Algunas respuestas de error de DENUE vienen como JSON con mensaje."""

    error: str | None = None
    mensaje: str | None = None
