"""Configuración del proyecto — Pydantic Settings que lee `.env`.

Uso:
    from src.core.config import get_settings
    settings = get_settings()
    print(settings.DATABASE_URL)

`get_settings()` está cacheada con `lru_cache` — se construye una sola vez por proceso.
"""

from __future__ import annotations

from functools import lru_cache
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

Environment = Literal["development", "staging", "production"]
LogLevel = Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]


class Settings(BaseSettings):
    """Variables de entorno tipadas y validadas en boot."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",  # ignora vars del entorno no declaradas aquí
        case_sensitive=True,
    )

    # ---------- Entorno ----------
    APP_NAME: str = "CRM-Granos-MX"
    ENVIRONMENT: Environment = "development"
    LOG_LEVEL: LogLevel = "INFO"

    # ---------- Base de datos ----------
    DATABASE_URL: str = Field(
        ..., description="URL completa de Postgres con driver psycopg"
    )
    DATABASE_ECHO: bool = False

    # ---------- INEGI / DENUE ----------
    INEGI_DENUE_TOKEN: str = Field(..., description="Token gratuito de INEGI DENUE API")

    # ---------- Google Cloud / Places API ----------
    GOOGLE_PLACES_API_KEY: str = ""
    MONTHLY_BUDGET_USD: float = 100.0

    # ---------- Auth & seguridad ----------
    SECRET_KEY: str = ""
    JWT_SECRET_KEY: str = ""
    JWT_EXPIRE_MINUTES: int = 480
    RECOVERY_MASTER_KEY: str = ""

    # ---------- SMTP ----------
    SMTP_HOST: str = ""
    SMTP_PORT: int = 587
    SMTP_USER: str = ""
    SMTP_PASS: str = ""
    SMTP_FROM: str = ""

    # ---------- Handoff a comercial-app v2 (futuro) ----------
    INTERNAL_TOKEN: str = ""
    COMERCIAL_V2_URL: str = ""

    # ---------- CORS ----------
    CORS_ORIGINS: str = "http://localhost:5173,http://localhost:8000"

    @property
    def cors_origins_list(self) -> list[str]:
        """Devuelve la lista de origins parsing la string separada por comas."""
        return [o.strip() for o in self.CORS_ORIGINS.split(",") if o.strip()]

    @property
    def is_production(self) -> bool:
        return self.ENVIRONMENT == "production"


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Punto único de acceso a la configuración. Usa esto, NO instancies Settings()
    directamente (rompe el caché y vuelve a leer .env)."""
    return Settings()  # type: ignore[call-arg]  # los Field(...) los rellena Pydantic
