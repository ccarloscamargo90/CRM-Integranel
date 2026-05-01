"""Tests del cliente DENUE con httpx.MockTransport (sin red real)."""

from __future__ import annotations

import json

import httpx
import pytest

from src.ingestion.denue import DenueClient, DenueError


def _make_client_con_handler(handler):
    """Crea un DenueClient con su httpx.Client reemplazado por MockTransport."""
    transport = httpx.MockTransport(handler)
    cli = DenueClient(timeout=5.0)
    # Reemplaza el _client interno; cierra el real primero.
    cli._client.close()
    cli._client = httpx.Client(transport=transport, headers=cli._client.headers)
    cli._MIN_INTERVALO_SEG = 0  # sin throttle en tests
    return cli


def test_cuantificar_parsea_lista():
    def handler(request: httpx.Request) -> httpx.Response:
        body = json.dumps([
            {"AE": "311830", "AG": "23", "Total": "933"},
            {"AE": "311830", "AG": "27", "Total": "2370"},
        ])
        return httpx.Response(200, content=body, headers={"content-type": "application/json"})

    cli = _make_client_con_handler(handler)
    totales = cli.cuantificar("311830")
    assert totales == {"23": 933, "27": 2370}


def test_get_json_falla_con_html():
    """Si DENUE devuelve HTML (URL obsoleta), se propaga error legible."""
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=b"<html>404</html>", headers={"content-type": "text/html"})

    cli = _make_client_con_handler(handler)
    with pytest.raises(DenueError, match="HTML"):
        cli.cuantificar("311830")


def test_get_json_falla_con_4xx_no_retry():
    """4xx no es transient — se propaga sin retry."""
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(400, content=b"Bad Request", headers={"content-type": "text/plain"})

    cli = _make_client_con_handler(handler)
    with pytest.raises(DenueError, match="400"):
        cli.cuantificar("311830")


def test_get_json_reintenta_con_5xx():
    """5xx es retryable — al 3er intento dentro del MockTransport, OK."""
    intentos = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        intentos["n"] += 1
        if intentos["n"] < 3:
            return httpx.Response(503, content=b"Service Unavailable")
        body = json.dumps([{"AE": "311830", "AG": "23", "Total": "100"}])
        return httpx.Response(200, content=body, headers={"content-type": "application/json"})

    cli = _make_client_con_handler(handler)
    totales = cli.cuantificar("311830")
    assert intentos["n"] == 3
    assert totales == {"23": 100}


def test_safe_url_oculta_token():
    """No echa el token al loguear."""
    cli = DenueClient(timeout=5.0)
    cli._token = "secret-token-12345"
    url = "https://example.com/path/secret-token-12345?x=1"
    safe = cli._safe_url(url)
    assert "secret-token-12345" not in safe
    assert "***" in safe
    cli.close()


def test_descargar_zip_entidad_y_iter_csv():
    """Mock de ZIP en memoria + filtro SCIAN."""
    import csv as _csv
    import io
    import zipfile

    # Construir CSV de prueba con headers oficiales DENUE
    csv_buffer = io.StringIO()
    writer = _csv.writer(csv_buffer)
    writer.writerow(
        [
            "id", "clee", "nom_estab", "raz_social", "codigo_act", "nombre_act",
            "per_ocu", "tipo_vial", "nom_vial", "tipo_v_e_1", "nom_v_e_1",
            "tipo_v_e_2", "nom_v_e_2", "tipo_v_e_3", "nom_v_e_3",
            "numero_ext", "letra_ext", "edificio", "edificio_e",
            "numero_int", "letra_int", "tipo_asent", "nomb_asent",
            "tipoCenCom", "nom_CenCom", "num_local", "cod_postal",
            "cve_ent", "entidad", "cve_mun", "municipio", "localidad",
            "ageb", "manzana", "telefono", "correo_e", "www",
            "tipo_unidad", "latitud", "longitud", "fecha_alta",
        ]
    )
    writer.writerow([
        "1", "04003311830000421000000000U2", "TORTILLERIA A", "",
        "311830", "Elaboración tortillas",
        "0 a 5 personas", "CALLE", "REFORMA", "", "", "", "", "", "",
        "100", "", "", "", "", "", "COLONIA", "CENTRO", "", "", "", "24000",
        "04", "Campeche", "003", "Carmen", "Carmen", "0001", "020",
        "9831234567", "", "", "Fijo", "18.6", "-91.7", "2018-05",
    ])
    writer.writerow([
        "2", "04003311830000422000000000U3", "OTRA INDUSTRIA", "",
        "999999", "Otra cosa",
        "0 a 5 personas", "CALLE", "PIRATA", "", "", "", "", "", "",
        "1", "", "", "", "", "", "COLONIA", "CENTRO", "", "", "", "24000",
        "04", "Campeche", "003", "Carmen", "Carmen", "0001", "020",
        "", "", "", "Fijo", "18.6", "-91.7", "2010-01",
    ])

    # Empaquetar en ZIP con la estructura real DENUE
    zip_bytes = io.BytesIO()
    with zipfile.ZipFile(zip_bytes, "w") as zf:
        zf.writestr(
            "conjunto_de_datos/denue_inegi_04_.csv",
            csv_buffer.getvalue().encode("latin-1"),
        )
    zip_payload = zip_bytes.getvalue()

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            content=zip_payload,
            headers={"content-type": "application/x-zip-compressed"},
        )

    cli = _make_client_con_handler(handler)
    # Sin filtro: 2 filas
    rows = list(cli.iter_csv_entidad("04"))
    assert len(rows) == 2
    # Con filtro SCIAN 311830: solo 1 fila
    rows_filtered = list(cli.iter_csv_entidad("04", scian_filter={"311830"}))
    assert len(rows_filtered) == 1
    assert rows_filtered[0]["clee"] == "04003311830000421000000000U2"
