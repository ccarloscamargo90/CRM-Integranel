"""Logging con loguru — configuración centralizada.

Llamar `setup_logging()` una sola vez al boot del proceso (en `main.py` de FastAPI,
o al inicio de scripts CLI).

Después, en cualquier módulo:
    from loguru import logger
    logger.info("mensaje")
"""

from __future__ import annotations

import sys
from pathlib import Path

from loguru import logger

from .config import get_settings


def setup_logging() -> None:
    """Configura sinks de loguru: consola colorida + archivo rotativo + JSON estructurado.

    Idempotente: si se llama múltiples veces, los handlers viejos se reemplazan.
    """
    settings = get_settings()

    # Limpia handlers default
    logger.remove()

    # ---------- Consola ----------
    logger.add(
        sys.stderr,
        level=settings.LOG_LEVEL,
        format=(
            "<green>{time:YYYY-MM-DD HH:mm:ss}</green> | "
            "<level>{level: <8}</level> | "
            "<cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - "
            "<level>{message}</level>"
        ),
        colorize=True,
        enqueue=False,
    )

    # ---------- Archivo (DEBUG completo) ----------
    logs_dir = Path("logs")
    logs_dir.mkdir(exist_ok=True)

    logger.add(
        logs_dir / "app.log",
        level="DEBUG",
        format="{time:YYYY-MM-DD HH:mm:ss.SSS} | {level: <8} | {name}:{function}:{line} - {message}",
        rotation="10 MB",
        retention="30 days",
        compression="zip",
        enqueue=True,  # async-safe
    )

    # ---------- JSON estructurado para producción ----------
    if settings.is_production:
        logger.add(
            logs_dir / "app.jsonl",
            level="INFO",
            serialize=True,
            rotation="50 MB",
            retention="90 days",
            enqueue=True,
        )

    logger.info(
        "Logging configurado",
        extra={"env": settings.ENVIRONMENT, "level": settings.LOG_LEVEL},
    )
