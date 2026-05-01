"""Tests endpoints /prospectos/* — listado, detalle, contacto."""

from __future__ import annotations

from collections.abc import Generator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from src.api.auth import hash_password
from src.api.dependencies import get_db
from src.api.main import app
from src.core.models import Establecimiento, Interaccion, Usuario, Vendedor


@pytest.fixture
def client(db: Session) -> Generator[TestClient, None, None]:
    def _override_get_db():
        try:
            yield db
        finally:
            pass

    app.dependency_overrides[get_db] = _override_get_db
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


@pytest.fixture
def vendedor_a(db: Session) -> Vendedor:
    v = Vendedor(codigo="V001", nombre="Vendedor A", activo=True)
    db.add(v)
    db.flush()
    return v


@pytest.fixture
def vendedor_b(db: Session) -> Vendedor:
    v = Vendedor(codigo="V002", nombre="Vendedor B", activo=True)
    db.add(v)
    db.flush()
    return v


@pytest.fixture
def admin_user(db: Session) -> Usuario:
    u = Usuario(
        username="api_admin",
        password_hash=hash_password("Admin#123"),
        nombre="Admin",
        rol="admin",
        activo=True,
    )
    db.add(u)
    db.flush()
    return u


@pytest.fixture
def vendedor_user_a(db: Session, vendedor_a: Vendedor) -> Usuario:
    u = Usuario(
        username="vend_a",
        password_hash=hash_password("Vend#123"),
        nombre="Vendedor A login",
        rol="vendedor",
        vendedor_id=vendedor_a.id,
        activo=True,
    )
    db.add(u)
    db.flush()
    return u


@pytest.fixture
def prospecto_de_a(db: Session, vendedor_a: Vendedor) -> Establecimiento:
    e = Establecimiento(
        clee="11000000311830P00001",
        hash_dedup="hash_test_a_001",
        nombre="Tortillería La Prueba A",
        nombre_norm="tortilleria la prueba a",
        scian_codigo="311830",
        canales=["Tortillerias"],
        estado_pipeline="no_contactado",
        riesgo_69b=False,
        vendedor_id=vendedor_a.id,
        score_prioridad=75.0,
        segmento_abc="A",
    )
    db.add(e)
    db.flush()
    return e


@pytest.fixture
def prospecto_de_b(db: Session, vendedor_b: Vendedor) -> Establecimiento:
    e = Establecimiento(
        clee="11000000311830P00002",
        hash_dedup="hash_test_b_002",
        nombre="Tortillería La Prueba B",
        nombre_norm="tortilleria la prueba b",
        scian_codigo="311830",
        canales=["Tortillerias"],
        estado_pipeline="no_contactado",
        riesgo_69b=False,
        vendedor_id=vendedor_b.id,
        score_prioridad=60.0,
        segmento_abc="B",
    )
    db.add(e)
    db.flush()
    return e


def _login_as(client: TestClient, username: str, password: str):
    res = client.post("/auth/login", json={"username": username, "password": password})
    assert res.status_code == 200, res.text


def test_listar_sin_auth_devuelve_401(client: TestClient):
    res = client.get("/prospectos")
    assert res.status_code == 401


def test_admin_ve_todos_los_prospectos(
    client: TestClient,
    admin_user: Usuario,
    prospecto_de_a: Establecimiento,
    prospecto_de_b: Establecimiento,
):
    _login_as(client, "api_admin", "Admin#123")
    res = client.get("/prospectos")
    assert res.status_code == 200
    body = res.json()
    nombres = {p["nombre"] for p in body["items"]}
    assert "Tortillería La Prueba A" in nombres
    assert "Tortillería La Prueba B" in nombres


def test_vendedor_solo_ve_los_suyos(
    client: TestClient,
    vendedor_user_a: Usuario,
    prospecto_de_a: Establecimiento,
    prospecto_de_b: Establecimiento,
):
    _login_as(client, "vend_a", "Vend#123")
    res = client.get("/prospectos")
    assert res.status_code == 200
    body = res.json()
    nombres = {p["nombre"] for p in body["items"]}
    assert "Tortillería La Prueba A" in nombres
    assert "Tortillería La Prueba B" not in nombres


def test_listar_filtro_segmento(
    client: TestClient,
    admin_user: Usuario,
    prospecto_de_a: Establecimiento,
    prospecto_de_b: Establecimiento,
):
    _login_as(client, "api_admin", "Admin#123")
    res = client.get("/prospectos", params={"segmento": "A"})
    assert res.status_code == 200
    nombres = {p["nombre"] for p in res.json()["items"]}
    assert "Tortillería La Prueba A" in nombres
    assert "Tortillería La Prueba B" not in nombres


def test_listar_filtro_canal(
    client: TestClient,
    admin_user: Usuario,
    prospecto_de_a: Establecimiento,
):
    _login_as(client, "api_admin", "Admin#123")
    res = client.get("/prospectos", params={"canal": "Tortillerias"})
    assert res.status_code == 200
    items = res.json()["items"]
    assert all("Tortillerias" in p["canales"] for p in items)


def test_detalle_existente_ok(
    client: TestClient,
    admin_user: Usuario,
    prospecto_de_a: Establecimiento,
):
    _login_as(client, "api_admin", "Admin#123")
    res = client.get(f"/prospectos/{prospecto_de_a.id}")
    assert res.status_code == 200
    body = res.json()
    assert body["id"] == prospecto_de_a.id
    assert body["nombre"] == "Tortillería La Prueba A"


def test_detalle_inexistente_404(client: TestClient, admin_user: Usuario):
    _login_as(client, "api_admin", "Admin#123")
    res = client.get("/prospectos/99999999")
    assert res.status_code == 404


def test_vendedor_no_puede_ver_detalle_ajeno(
    client: TestClient,
    vendedor_user_a: Usuario,
    prospecto_de_b: Establecimiento,
):
    _login_as(client, "vend_a", "Vend#123")
    res = client.get(f"/prospectos/{prospecto_de_b.id}")
    assert res.status_code == 403


def test_registrar_contacto_crea_interaccion(
    client: TestClient,
    db: Session,
    vendedor_user_a: Usuario,
    prospecto_de_a: Establecimiento,
):
    _login_as(client, "vend_a", "Vend#123")
    res = client.post(
        f"/prospectos/{prospecto_de_a.id}/contacto",
        json={
            "tipo": "llamada",
            "resultado": "Conversación cordial, pidió cotización",
            "siguiente_paso": "Enviar cotización mañana",
            "contacto_persona": "Juan Pérez",
        },
    )
    assert res.status_code == 201
    body = res.json()
    assert "interaccion_id" in body
    # Verifica que efectivamente se creó la interacción
    inter = db.get(Interaccion, body["interaccion_id"])
    assert inter is not None
    assert inter.tipo == "llamada"
    assert inter.establecimiento_id == prospecto_de_a.id


def test_registrar_contacto_cambia_pipeline(
    client: TestClient,
    db: Session,
    vendedor_user_a: Usuario,
    prospecto_de_a: Establecimiento,
):
    assert prospecto_de_a.estado_pipeline == "no_contactado"
    _login_as(client, "vend_a", "Vend#123")
    res = client.post(
        f"/prospectos/{prospecto_de_a.id}/contacto",
        json={
            "tipo": "visita",
            "nuevo_estado_pipeline": "contactado",
        },
    )
    assert res.status_code == 201
    assert res.json()["estado_pipeline"] == "contactado"
    db.refresh(prospecto_de_a)
    assert prospecto_de_a.estado_pipeline == "contactado"


def test_registrar_contacto_prospecto_ajeno_403(
    client: TestClient,
    vendedor_user_a: Usuario,
    prospecto_de_b: Establecimiento,
):
    _login_as(client, "vend_a", "Vend#123")
    res = client.post(
        f"/prospectos/{prospecto_de_b.id}/contacto",
        json={"tipo": "llamada"},
    )
    assert res.status_code == 403


def test_registrar_contacto_tipo_invalido_422(
    client: TestClient,
    vendedor_user_a: Usuario,
    prospecto_de_a: Establecimiento,
):
    _login_as(client, "vend_a", "Vend#123")
    res = client.post(
        f"/prospectos/{prospecto_de_a.id}/contacto",
        json={"tipo": "ritual_satanico"},
    )
    assert res.status_code == 422
