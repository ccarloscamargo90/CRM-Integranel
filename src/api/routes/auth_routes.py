"""Endpoints de autenticación: /login, /logout, /me."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Response, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from src.api.auth import crear_jwt, verify_password
from src.api.dependencies import COOKIE_NAME, get_current_user, get_db
from src.core.config import get_settings
from src.core.models import Usuario

router = APIRouter(prefix="/auth", tags=["auth"])


class LoginRequest(BaseModel):
    username: str
    password: str


class UserOut(BaseModel):
    id: int
    username: str
    nombre: str
    email: str | None = None
    rol: str
    vendedor_id: int | None = None


@router.post("/login", response_model=UserOut)
def login(
    body: LoginRequest,
    response: Response,
    db: Annotated[Session, Depends(get_db)],
) -> Usuario:
    """Login con username + password. Setea cookie httpOnly con JWT."""
    user = db.query(Usuario).filter(Usuario.username == body.username).first()
    if not user or not user.activo or not verify_password(body.password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Credenciales inválidas",
        )

    token = crear_jwt(username=user.username, rol=user.rol, vendedor_id=user.vendedor_id)
    settings = get_settings()
    response.set_cookie(
        key=COOKIE_NAME,
        value=token,
        max_age=settings.JWT_EXPIRE_MINUTES * 60,
        httponly=True,
        secure=settings.is_production,  # Secure cookie solo en prod (HTTPS)
        samesite="lax",
    )
    return user


@router.post("/logout")
def logout(response: Response) -> dict[str, str]:
    response.delete_cookie(COOKIE_NAME)
    return {"detail": "Sesión cerrada"}


@router.get("/me", response_model=UserOut)
def me(user: Annotated[Usuario, Depends(get_current_user)]) -> Usuario:
    return user
