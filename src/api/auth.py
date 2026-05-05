"""Auth — JWT + bcrypt + 3 roles (admin / vendedor / jefe).

Diseño:
- Password hash con bcrypt (passlib).
- Token JWT en cookie httpOnly + Secure (cookie name: `crm_token`).
- Expiración: `JWT_EXPIRE_MINUTES` (default 480 = 8 horas).
- Roles validados con dependencia `require_role(...)`.

NO usamos OAuth / SSO en esta versión; la auth es puramente interna.
"""

from __future__ import annotations

import datetime as dt
from typing import Any

import bcrypt
import jwt as pyjwt
from jwt.exceptions import PyJWTError

from src.core.config import get_settings


def hash_password(plain: str) -> str:
    """Hash bcrypt con cost factor 12. Trunca a 72 bytes (límite de bcrypt)."""
    return bcrypt.hashpw(plain.encode("utf-8")[:72], bcrypt.gensalt(rounds=12)).decode("utf-8")


def verify_password(plain: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(plain.encode("utf-8")[:72], hashed.encode("utf-8"))
    except Exception:
        return False


def crear_jwt(*, username: str, rol: str, vendedor_id: int | None = None) -> str:
    """Genera token con expiración configurada."""
    settings = get_settings()
    if not settings.JWT_SECRET_KEY:
        raise RuntimeError("JWT_SECRET_KEY no configurado en .env")

    ahora = dt.datetime.now(dt.UTC)
    payload = {
        "sub": username,
        "rol": rol,
        "vendedor_id": vendedor_id,
        "iat": ahora,
        "exp": ahora + dt.timedelta(minutes=settings.JWT_EXPIRE_MINUTES),
    }
    return pyjwt.encode(payload, settings.JWT_SECRET_KEY, algorithm="HS256")


def decodificar_jwt(token: str) -> dict[str, Any] | None:
    """Devuelve el payload o None si el token es inválido/expirado."""
    settings = get_settings()
    if not settings.JWT_SECRET_KEY:
        return None
    try:
        return pyjwt.decode(token, settings.JWT_SECRET_KEY, algorithms=["HS256"])
    except PyJWTError:
        return None
