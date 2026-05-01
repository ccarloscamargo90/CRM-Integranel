"""Dependencias FastAPI — DB session, usuario actual, validación de rol.

Uso:
    from fastapi import Depends
    from src.api.dependencies import get_db, get_current_user, require_role

    @app.get("/prospectos")
    def listar(db: Session = Depends(get_db), user = Depends(require_role("admin","vendedor","jefe"))):
        ...
"""

from __future__ import annotations

from collections.abc import Generator
from typing import Annotated

from fastapi import Cookie, Depends, HTTPException, status
from sqlalchemy.orm import Session

from src.api.auth import decodificar_jwt
from src.core.db import SessionLocal
from src.core.models import Usuario

COOKIE_NAME = "crm_token"


def get_db() -> Generator[Session, None, None]:
    """Sesión SQLAlchemy por request, siempre se cierra."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def get_current_user(
    db: Annotated[Session, Depends(get_db)],
    crm_token: Annotated[str | None, Cookie()] = None,
) -> Usuario:
    """Verifica el JWT en cookie y devuelve el Usuario activo.

    Levanta 401 si no hay token, está expirado, o el usuario está inactivo.
    """
    if not crm_token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="No autenticado",
        )
    payload = decodificar_jwt(crm_token)
    if not payload:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token inválido o expirado",
        )
    username = payload.get("sub")
    user = db.query(Usuario).filter(Usuario.username == username).first()
    if not user or not user.activo:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Usuario inactivo o no existe",
        )
    return user


def require_role(*roles_permitidos: str):
    """Factory de dependencia que valida que el usuario tenga uno de los roles."""

    def _check(
        user: Annotated[Usuario, Depends(get_current_user)],
    ) -> Usuario:
        if user.rol not in roles_permitidos:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Rol '{user.rol}' no autorizado para esta acción",
            )
        return user

    return _check
