"""App FastAPI — punto de entrada para uvicorn / gunicorn / Render."""

from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from loguru import logger

from src.api import web
from src.api.routes import auth_routes, prospectos
from src.core.config import get_settings
from src.core.logging import setup_logging


@asynccontextmanager
async def lifespan(app: FastAPI):
    setup_logging()
    settings = get_settings()
    logger.info(
        "API arrancando: env={env} db={db}",
        env=settings.ENVIRONMENT,
        db=settings.DATABASE_URL.split("@")[-1] if "@" in settings.DATABASE_URL else settings.DATABASE_URL,
    )
    yield
    logger.info("API apagándose")


app = FastAPI(
    title="CRM-Granos-MX API",
    version="0.1.0",
    description=(
        "API REST del Sistema de Inteligencia Comercial dual de Intergranel. "
        "Maneja prospectos en 4 canales (Tortillerías, Alimento Balanceado, "
        "Forrajeras, Asociaciones) en 16 entidades priorizadas. "
        "Cumple LFPDPPP 2025 con bitácora compliance_log y derechos ARCO."
    ),
    lifespan=lifespan,
)

settings = get_settings()
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE"],
    allow_headers=["*"],
)


@app.get("/health", tags=["health"])
def health() -> JSONResponse:
    return JSONResponse({"status": "ok", "version": "0.1.0", "env": settings.ENVIRONMENT})


# Static (CSS custom — todo lo demás vía CDN)
_STATIC_DIR = Path(__file__).parent / "static"
app.mount("/static", StaticFiles(directory=str(_STATIC_DIR)), name="static")

# Routers — JSON API + HTML web
app.include_router(auth_routes.router)
app.include_router(prospectos.router)
app.include_router(web.router)
