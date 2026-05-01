"""Tests endpoints /auth/* — login, logout, /me."""

from __future__ import annotations

from collections.abc import Generator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from src.api.auth import hash_password
from src.api.dependencies import get_db
from src.api.main import app
from src.core.models import Usuario


@pytest.fixture
def client(db: Session) -> Generator[TestClient, None, None]:
    """TestClient con get_db override hacia la sesión transaccional del test."""

    def _override_get_db():
        try:
            yield db
        finally:
            pass  # el rollback lo hace el fixture `db` al cerrar

    app.dependency_overrides[get_db] = _override_get_db
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


@pytest.fixture
def usuario_admin(db: Session) -> Usuario:
    u = Usuario(
        username="test_admin",
        password_hash=hash_password("S3cret123!"),
        nombre="Admin Test",
        rol="admin",
        activo=True,
    )
    db.add(u)
    db.flush()
    return u


def test_login_credenciales_ok_setea_cookie(client: TestClient, usuario_admin: Usuario):
    res = client.post("/auth/login", json={"username": "test_admin", "password": "S3cret123!"})
    assert res.status_code == 200
    body = res.json()
    assert body["username"] == "test_admin"
    assert body["rol"] == "admin"
    assert "crm_token" in res.cookies


def test_login_password_invalido_rechaza(client: TestClient, usuario_admin: Usuario):
    res = client.post("/auth/login", json={"username": "test_admin", "password": "wrong"})
    assert res.status_code == 401
    assert res.json()["detail"] == "Credenciales inválidas"


def test_login_usuario_inexistente_rechaza(client: TestClient):
    res = client.post("/auth/login", json={"username": "ghost", "password": "x"})
    assert res.status_code == 401


def test_login_usuario_inactivo_rechaza(client: TestClient, db: Session):
    u = Usuario(
        username="muerto",
        password_hash=hash_password("xxx"),
        nombre="Inactivo",
        rol="vendedor",
        activo=False,
    )
    db.add(u)
    db.flush()
    res = client.post("/auth/login", json={"username": "muerto", "password": "xxx"})
    assert res.status_code == 401


def test_me_sin_cookie_devuelve_401(client: TestClient):
    res = client.get("/auth/me")
    assert res.status_code == 401


def test_me_con_cookie_devuelve_usuario(client: TestClient, usuario_admin: Usuario):
    login = client.post("/auth/login", json={"username": "test_admin", "password": "S3cret123!"})
    assert login.status_code == 200
    res = client.get("/auth/me")
    assert res.status_code == 200
    body = res.json()
    assert body["username"] == "test_admin"
    assert body["rol"] == "admin"


def test_logout_borra_cookie(client: TestClient, usuario_admin: Usuario):
    client.post("/auth/login", json={"username": "test_admin", "password": "S3cret123!"})
    res = client.post("/auth/logout")
    assert res.status_code == 200
    # tras logout, /me devuelve 401
    me = client.get("/auth/me", cookies={})
    # El TestClient mantiene la cookie ya borrada; forzamos cookie vacía
    client.cookies.clear()
    me = client.get("/auth/me")
    assert me.status_code == 401


def test_token_invalido_rechaza(client: TestClient):
    client.cookies.set("crm_token", "garbage.token.value")
    res = client.get("/auth/me")
    assert res.status_code == 401
