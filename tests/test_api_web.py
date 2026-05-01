"""Tests rutas HTML web (Jinja+HTMX) — login, dashboard, lista, detalle, mapa."""

from __future__ import annotations

from collections.abc import Generator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from src.api.auth import hash_password
from src.api.dependencies import get_db
from src.api.main import app
from src.core.models import Establecimiento, Usuario, Vendedor


@pytest.fixture
def client(db: Session) -> Generator[TestClient, None, None]:
    def _override_get_db():
        try:
            yield db
        finally:
            pass

    app.dependency_overrides[get_db] = _override_get_db
    with TestClient(app, follow_redirects=False) as c:
        yield c
    app.dependency_overrides.clear()


@pytest.fixture
def admin_user(db: Session) -> Usuario:
    u = Usuario(
        username="web_admin",
        password_hash=hash_password("Web#123"),
        nombre="Admin Web",
        rol="admin",
        activo=True,
    )
    db.add(u)
    db.flush()
    return u


@pytest.fixture
def vendedor_user(db: Session) -> Usuario:
    v = Vendedor(codigo="VW001", nombre="Vendedor Web", activo=True)
    db.add(v)
    db.flush()
    u = Usuario(
        username="web_vend",
        password_hash=hash_password("Web#123"),
        nombre="Vendedor Web",
        rol="vendedor",
        vendedor_id=v.id,
        activo=True,
    )
    db.add(u)
    db.flush()
    return u


@pytest.fixture
def prospecto(db: Session, admin_user: Usuario) -> Establecimiento:
    e = Establecimiento(
        clee="11000000311830W00001",
        hash_dedup="hash_web_001",
        nombre="Tortillería Web Test",
        nombre_norm="tortilleria web test",
        scian_codigo="311830",
        canales=["Tortillerias"],
        estado="Querétaro",
        estado_codigo="22",
        municipio="Querétaro",
        latitud=20.5888,
        longitud=-100.3899,
        score_prioridad=82.5,
        segmento_abc="A",
        estado_pipeline="no_contactado",
        riesgo_69b=False,
    )
    db.add(e)
    db.flush()
    return e


def _login_html(client: TestClient, username: str, password: str):
    res = client.post("/login", data={"username": username, "password": password})
    assert res.status_code == 303, res.text
    return res


# =============================================================================
# Login form
# =============================================================================
def test_get_login_renderiza_form(client: TestClient):
    res = client.get("/login")
    assert res.status_code == 200
    assert "CRM Granos MX" in res.text
    assert 'name="username"' in res.text
    assert 'name="password"' in res.text


def test_post_login_ok_redirige_y_setea_cookie(client: TestClient, admin_user: Usuario):
    res = client.post("/login", data={"username": "web_admin", "password": "Web#123"})
    assert res.status_code == 303
    assert res.headers["location"] == "/"
    assert "crm_token" in res.cookies


def test_post_login_password_invalido_renderiza_error(client: TestClient, admin_user: Usuario):
    res = client.post("/login", data={"username": "web_admin", "password": "wrong"})
    assert res.status_code == 401
    assert "Credenciales inválidas" in res.text


# =============================================================================
# Dashboard
# =============================================================================
def test_dashboard_sin_auth_redirige_login(client: TestClient):
    res = client.get("/")
    assert res.status_code == 303
    assert res.headers["location"] == "/login"


def test_dashboard_con_auth_renderiza(client: TestClient, admin_user: Usuario, prospecto):
    _login_html(client, "web_admin", "Web#123")
    res = client.get("/")
    assert res.status_code == 200
    assert "Dashboard" in res.text
    assert "Tortillería Web Test" in res.text  # aparece en top10
    assert "Distribución por canal" in res.text


# =============================================================================
# Lista
# =============================================================================
def test_lista_sin_auth_redirige(client: TestClient):
    res = client.get("/lista")
    assert res.status_code == 303
    assert res.headers["location"] == "/login"


def test_lista_renderiza_tabla(client: TestClient, admin_user: Usuario, prospecto):
    _login_html(client, "web_admin", "Web#123")
    res = client.get("/lista")
    assert res.status_code == 200
    assert "Prospectos" in res.text
    assert "Tortillería Web Test" in res.text


def test_lista_fragment_devuelve_solo_filas(
    client: TestClient, admin_user: Usuario, prospecto
):
    _login_html(client, "web_admin", "Web#123")
    res = client.get("/lista/fragment", params={"canal": "Tortillerias"})
    assert res.status_code == 200
    # El fragment solo devuelve <tr> (no <html>/<body>)
    assert "<html" not in res.text.lower()
    assert "Tortillería Web Test" in res.text


def test_lista_fragment_sin_auth_devuelve_401(client: TestClient):
    res = client.get("/lista/fragment")
    assert res.status_code == 401


def test_lista_filtro_busqueda_q(client: TestClient, admin_user: Usuario, prospecto):
    _login_html(client, "web_admin", "Web#123")
    res = client.get("/lista", params={"q": "Web Test"})
    assert res.status_code == 200
    assert "Tortillería Web Test" in res.text

    res = client.get("/lista", params={"q": "ZZZNoExiste"})
    assert "Sin resultados" in res.text


# =============================================================================
# Detalle + form contacto
# =============================================================================
def test_detalle_renderiza_y_loguea_compliance(
    client: TestClient, db: Session, admin_user: Usuario, prospecto
):
    _login_html(client, "web_admin", "Web#123")
    res = client.get(f"/prospecto/{prospecto.id}")
    assert res.status_code == 200
    assert "Tortillería Web Test" in res.text
    assert "Querétaro" in res.text
    assert "Registrar contacto" in res.text


def test_detalle_404_si_no_existe(client: TestClient, admin_user: Usuario):
    _login_html(client, "web_admin", "Web#123")
    res = client.get("/prospecto/99999999")
    assert res.status_code == 404


def test_post_contacto_redirige_con_mensaje(
    client: TestClient, db: Session, admin_user: Usuario, prospecto
):
    _login_html(client, "web_admin", "Web#123")
    res = client.post(
        f"/prospecto/{prospecto.id}/contacto",
        data={
            "tipo": "llamada",
            "resultado": "Cotización pendiente",
            "nuevo_estado_pipeline": "contactado",
        },
    )
    assert res.status_code == 303
    assert "mensaje=Contacto+registrado" in res.headers["location"]
    db.refresh(prospecto)
    assert prospecto.estado_pipeline == "contactado"


def test_post_contacto_tipo_invalido_redirige_error(
    client: TestClient, admin_user: Usuario, prospecto
):
    _login_html(client, "web_admin", "Web#123")
    res = client.post(
        f"/prospecto/{prospecto.id}/contacto",
        data={"tipo": "ritual_satanico"},
    )
    assert res.status_code == 303
    assert "mensaje_tipo=err" in res.headers["location"]


# =============================================================================
# Mapa + endpoint mapa-data
# =============================================================================
def test_mapa_renderiza(client: TestClient, admin_user: Usuario):
    _login_html(client, "web_admin", "Web#123")
    res = client.get("/mapa")
    assert res.status_code == 200
    assert "leaflet" in res.text.lower()
    assert "/api/mapa-data" in res.text


def test_mapa_data_devuelve_json(
    client: TestClient, admin_user: Usuario, prospecto
):
    _login_html(client, "web_admin", "Web#123")
    res = client.get("/api/mapa-data")
    assert res.status_code == 200
    body = res.json()
    assert "items" in body
    nombres = {i["nombre"] for i in body["items"]}
    assert "Tortillería Web Test" in nombres
    item = next(i for i in body["items"] if i["nombre"] == "Tortillería Web Test")
    assert abs(item["lat"] - 20.5888) < 1e-3
    assert abs(item["lon"] - (-100.3899)) < 1e-3
    assert item["segmento_abc"] == "A"


def test_mapa_data_filtra_por_estado(
    client: TestClient, admin_user: Usuario, prospecto
):
    _login_html(client, "web_admin", "Web#123")
    res = client.get("/api/mapa-data", params={"estado_codigo": "22"})
    assert res.status_code == 200
    nombres = {i["nombre"] for i in res.json()["items"]}
    assert "Tortillería Web Test" in nombres

    res = client.get("/api/mapa-data", params={"estado_codigo": "01"})
    nombres = {i["nombre"] for i in res.json()["items"]}
    assert "Tortillería Web Test" not in nombres


def test_mapa_data_sin_auth_devuelve_401(client: TestClient):
    res = client.get("/api/mapa-data")
    assert res.status_code == 401


# =============================================================================
# Logout
# =============================================================================
def test_logout_borra_cookie_y_redirige(client: TestClient, admin_user: Usuario):
    _login_html(client, "web_admin", "Web#123")
    res = client.post("/logout")
    assert res.status_code == 303
    assert res.headers["location"] == "/login"
    # Tras logout, el dashboard redirige a login
    client.cookies.clear()
    res2 = client.get("/")
    assert res2.status_code == 303
    assert res2.headers["location"] == "/login"
