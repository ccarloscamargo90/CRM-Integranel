"""Rutas HTML server-rendered (Jinja+HTMX). Comparten cookie JWT con la API.

Diseño:
- `templates_env` y `Jinja2Templates` instanciados al final del archivo.
- Auth: si la cookie es inválida → 302 a /login.
- /login (GET, POST), /logout (POST), / (dashboard), /lista, /lista/fragment,
  /prospecto/{id}, /prospecto/{id}/contacto, /mapa, /api/mapa-data.
- Reutiliza la lógica de seguridad del API (vendedor solo ve lo suyo).
"""

from __future__ import annotations

from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Cookie, Depends, Form, HTTPException, Request, status
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse, Response
from fastapi.templating import Jinja2Templates
from sqlalchemy import and_, func, select
from sqlalchemy.orm import Session

from src.api.auth import crear_jwt, decodificar_jwt, verify_password
from src.api.dependencies import COOKIE_NAME, get_db
from src.compliance.lfpdppp import registrar_operacion
from src.core.config import get_settings
from src.core.constantes import CANALES, ENTIDADES_PRIORIZADAS
from src.core.models import (
    EnriquecimientoGoogle,
    Establecimiento,
    Interaccion,
    PipelineEtapaHistorial,
    Usuario,
)

router = APIRouter(tags=["web"])

TEMPLATES_DIR = Path(__file__).parent / "templates"
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))


# ============================================================================
# Auth helpers (web flavor — redirect en lugar de JSON 401)
# ============================================================================
def get_current_user_web(
    db: Annotated[Session, Depends(get_db)],
    crm_token: Annotated[str | None, Cookie()] = None,
) -> Usuario | None:
    """Devuelve Usuario activo o None. NO levanta excepción."""
    if not crm_token:
        return None
    payload = decodificar_jwt(crm_token)
    if not payload:
        return None
    user = db.query(Usuario).filter(Usuario.username == payload.get("sub")).first()
    return user if user and user.activo else None


def _filtros_vendedor(user: Usuario) -> list:
    """Filtros adicionales si el usuario es vendedor (solo ve sus prospectos)."""
    if user.rol == "vendedor" and user.vendedor_id:
        return [Establecimiento.vendedor_id == user.vendedor_id]
    return []


# ============================================================================
# Login / Logout HTML
# ============================================================================
@router.get("/login", response_class=HTMLResponse)
def login_form(request: Request, error: str | None = None):
    return templates.TemplateResponse(
        "login.html", {"request": request, "user": None, "error": error}
    )


@router.post("/login")
def login_submit(
    db: Annotated[Session, Depends(get_db)],
    username: Annotated[str, Form()],
    password: Annotated[str, Form()],
):
    user = db.query(Usuario).filter(Usuario.username == username).first()
    if not user or not user.activo or not verify_password(password, user.password_hash):
        return templates.TemplateResponse(
            "login.html",
            {"request": {}, "user": None, "error": "Credenciales inválidas"},
            status_code=status.HTTP_401_UNAUTHORIZED,
        )

    settings = get_settings()
    token = crear_jwt(username=user.username, rol=user.rol, vendedor_id=user.vendedor_id)
    response = RedirectResponse("/", status_code=status.HTTP_303_SEE_OTHER)
    response.set_cookie(
        key=COOKIE_NAME,
        value=token,
        max_age=settings.JWT_EXPIRE_MINUTES * 60,
        httponly=True,
        secure=settings.is_production,
        samesite="lax",
    )
    return response


@router.post("/logout")
def logout_submit() -> Response:
    response = RedirectResponse("/login", status_code=status.HTTP_303_SEE_OTHER)
    response.delete_cookie(COOKIE_NAME)
    return response


# ============================================================================
# Dashboard
# ============================================================================
@router.get("/", response_class=HTMLResponse)
def dashboard(
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[Usuario | None, Depends(get_current_user_web)],
):
    if not user:
        return RedirectResponse("/login", status_code=status.HTTP_303_SEE_OTHER)

    base_filters = _filtros_vendedor(user)

    def _count(*extra) -> int:
        q = select(func.count()).select_from(Establecimiento)
        all_filters = base_filters + list(extra)
        if all_filters:
            q = q.where(and_(*all_filters))
        return db.execute(q).scalar_one()

    total = _count()
    seg_a = _count(Establecimiento.segmento_abc == "A")
    seg_b = _count(Establecimiento.segmento_abc == "B")
    riesgo = _count(Establecimiento.riesgo_69b.is_(True))

    # Por canal — UNNEST sobre el array TEXT[]
    canal_q = select(
        func.unnest(Establecimiento.canales).label("canal"),
        func.count().label("c"),
    ).select_from(Establecimiento)
    if base_filters:
        canal_q = canal_q.where(and_(*base_filters))
    canal_q = canal_q.group_by("canal").order_by(func.count().desc())
    por_canal = db.execute(canal_q).all()

    # Por pipeline
    pipe_q = (
        select(Establecimiento.estado_pipeline, func.count())
        .select_from(Establecimiento)
        .group_by(Establecimiento.estado_pipeline)
        .order_by(func.count().desc())
    )
    if base_filters:
        pipe_q = pipe_q.where(and_(*base_filters))
    por_pipeline = db.execute(pipe_q).all()

    # Top 10
    top_q = select(Establecimiento)
    if base_filters:
        top_q = top_q.where(and_(*base_filters))
    top_q = top_q.order_by(Establecimiento.score_prioridad.desc().nulls_last()).limit(10)
    top10 = db.execute(top_q).scalars().all()

    return templates.TemplateResponse(
        "dashboard.html",
        {
            "request": request,
            "user": user,
            "active": "dashboard",
            "kpis": {
                "total": total,
                "segmento_a": seg_a,
                "segmento_b": seg_b,
                "riesgo_69b": riesgo,
                "por_canal": [(r.canal, r.c) for r in por_canal],
                "por_pipeline": [(r[0], r[1]) for r in por_pipeline],
            },
            "top10": top10,
        },
    )


# ============================================================================
# Lista de prospectos (con HTMX fragment)
# ============================================================================
def _query_lista(
    db: Session,
    user: Usuario,
    canal: str | None,
    segmento: str | None,
    estado_pipeline: str | None,
    estado_codigo: str | None,
    q: str | None,
    limit: int = 100,
):
    filtros = _filtros_vendedor(user)
    if canal:
        filtros.append(Establecimiento.canales.any(canal))
    if segmento:
        filtros.append(Establecimiento.segmento_abc == segmento)
    if estado_pipeline:
        filtros.append(Establecimiento.estado_pipeline == estado_pipeline)
    if estado_codigo:
        filtros.append(Establecimiento.estado_codigo == estado_codigo)
    if q:
        filtros.append(Establecimiento.nombre.ilike(f"%{q.strip()}%"))

    where = and_(*filtros) if filtros else None
    total_q = select(func.count()).select_from(Establecimiento)
    if where is not None:
        total_q = total_q.where(where)
    total = db.execute(total_q).scalar_one()

    q_items = select(Establecimiento)
    if where is not None:
        q_items = q_items.where(where)
    q_items = q_items.order_by(Establecimiento.score_prioridad.desc().nulls_last()).limit(limit)
    items = db.execute(q_items).scalars().all()
    return total, items


@router.get("/lista", response_class=HTMLResponse)
def lista(
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[Usuario | None, Depends(get_current_user_web)],
    canal: str | None = None,
    segmento: str | None = None,
    estado_pipeline: str | None = None,
    estado_codigo: str | None = None,
    q: str | None = None,
):
    if not user:
        return RedirectResponse("/login", status_code=status.HTTP_303_SEE_OTHER)
    total, items = _query_lista(
        db, user, canal, segmento, estado_pipeline, estado_codigo, q, limit=100
    )
    return templates.TemplateResponse(
        "lista.html",
        {
            "request": request,
            "user": user,
            "active": "lista",
            "items": items,
            "total": total,
            "canales": list(CANALES),
            "entidades": sorted(ENTIDADES_PRIORIZADAS.items()),
            "filtros": {
                "canal": canal,
                "segmento": segmento,
                "estado_pipeline": estado_pipeline,
                "estado_codigo": estado_codigo,
                "q": q,
            },
        },
    )


@router.get("/lista/fragment", response_class=HTMLResponse)
def lista_fragment(
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[Usuario | None, Depends(get_current_user_web)],
    canal: str | None = None,
    segmento: str | None = None,
    estado_pipeline: str | None = None,
    estado_codigo: str | None = None,
    q: str | None = None,
):
    """Devuelve solo las filas <tr> para que HTMX las swap en #tabla."""
    if not user:
        # En contexto HTMX, devolvemos 401 para que el cliente haga reload
        raise HTTPException(status_code=401, detail="Sesión expirada")
    _, items = _query_lista(
        db, user, canal, segmento, estado_pipeline, estado_codigo, q, limit=100
    )
    return templates.TemplateResponse(
        "partials/lista_filas.html",
        {"request": request, "user": user, "items": items},
    )


# ============================================================================
# Detalle del prospecto + form de contacto
# ============================================================================
@router.get("/prospecto/{prospecto_id}", response_class=HTMLResponse)
def detalle(
    request: Request,
    prospecto_id: int,
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[Usuario | None, Depends(get_current_user_web)],
    mensaje: str | None = None,
    mensaje_tipo: str | None = None,
):
    if not user:
        return RedirectResponse("/login", status_code=status.HTTP_303_SEE_OTHER)
    e = db.get(Establecimiento, prospecto_id)
    if not e:
        raise HTTPException(status_code=404, detail="Prospecto no existe")
    if user.rol == "vendedor" and user.vendedor_id and e.vendedor_id != user.vendedor_id:
        raise HTTPException(status_code=403, detail="Prospecto no asignado a ti")

    eg = db.get(EnriquecimientoGoogle, prospecto_id)
    p = {
        "id": e.id,
        "nombre": e.nombre,
        "razon_social": e.razon_social,
        "canales": list(e.canales or []),
        "etiquetas": list(e.etiquetas or []),
        "estado": e.estado,
        "estado_codigo": e.estado_codigo,
        "municipio": e.municipio,
        "direccion": e.direccion,
        "telefono": e.telefono,
        "email": e.email,
        "sitio_web": e.sitio_web,
        "latitud": e.latitud,
        "longitud": e.longitud,
        "score_prioridad": e.score_prioridad,
        "segmento_abc": e.segmento_abc,
        "estado_pipeline": e.estado_pipeline,
        "riesgo_69b": e.riesgo_69b,
        "google_rating": eg.google_rating if eg and eg.match_status == "match" else None,
        "google_user_rating_count": eg.google_user_rating_count
        if eg and eg.match_status == "match"
        else None,
    }

    historial = (
        db.execute(
            select(PipelineEtapaHistorial)
            .where(PipelineEtapaHistorial.establecimiento_id == prospecto_id)
            .order_by(PipelineEtapaHistorial.fecha.desc())
            .limit(20)
        )
        .scalars()
        .all()
    )
    interacciones = (
        db.execute(
            select(Interaccion)
            .where(Interaccion.establecimiento_id == prospecto_id)
            .order_by(Interaccion.fecha.desc())
            .limit(10)
        )
        .scalars()
        .all()
    )

    registrar_operacion(
        session=db,
        usuario_id=user.id,
        tipo_operacion="lectura_detalle_prospecto",
        finalidad="Vendedor consultó detalle del prospecto para gestión comercial",
        base_legal="Interés legítimo comercial B2B + relación laboral con Intergranel",
        establecimiento_ids=[prospecto_id],
        columnas_tocadas=["telefono", "email", "contacto_nombre", "contacto_telefono"],
    )
    db.commit()

    return templates.TemplateResponse(
        "detalle.html",
        {
            "request": request,
            "user": user,
            "active": "lista",
            "p": p,
            "historial": historial,
            "interacciones": interacciones,
            "mensaje": mensaje,
            "mensaje_tipo": mensaje_tipo,
        },
    )


@router.post("/prospecto/{prospecto_id}/contacto")
def detalle_contacto(
    prospecto_id: int,
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[Usuario | None, Depends(get_current_user_web)],
    tipo: Annotated[str, Form()],
    contacto_persona: Annotated[str | None, Form()] = None,
    resultado: Annotated[str | None, Form()] = None,
    siguiente_paso: Annotated[str | None, Form()] = None,
    nuevo_estado_pipeline: Annotated[str | None, Form()] = None,
    notas: Annotated[str | None, Form()] = None,
):
    if not user:
        return RedirectResponse("/login", status_code=status.HTTP_303_SEE_OTHER)
    if user.rol not in ("admin", "vendedor"):
        raise HTTPException(status_code=403, detail="No autorizado")

    e = db.get(Establecimiento, prospecto_id)
    if not e:
        raise HTTPException(status_code=404, detail="Prospecto no existe")
    if user.rol == "vendedor" and user.vendedor_id and e.vendedor_id != user.vendedor_id:
        raise HTTPException(status_code=403, detail="Prospecto no asignado a ti")

    if tipo not in (
        "visita", "llamada", "email", "whatsapp",
        "cotizacion", "pedido", "muestra", "seguimiento",
    ):
        return RedirectResponse(
            f"/prospecto/{prospecto_id}?mensaje=Tipo+invalido&mensaje_tipo=err",
            status_code=status.HTTP_303_SEE_OTHER,
        )

    db.add(Interaccion(
        establecimiento_id=prospecto_id,
        vendedor_id=user.vendedor_id,
        usuario_id=user.id,
        tipo=tipo,
        resultado=resultado,
        siguiente_paso=siguiente_paso,
        contacto_persona=contacto_persona,
        notas=notas,
    ))

    if nuevo_estado_pipeline and nuevo_estado_pipeline != e.estado_pipeline:
        db.add(PipelineEtapaHistorial(
            establecimiento_id=prospecto_id,
            usuario_id=user.id,
            etapa_anterior=e.estado_pipeline,
            etapa_nueva=nuevo_estado_pipeline,
            motivo=f"Tras interacción {tipo}",
        ))
        e.estado_pipeline = nuevo_estado_pipeline

    registrar_operacion(
        session=db,
        usuario_id=user.id,
        tipo_operacion="contacto_comercial",
        finalidad=f"Registro de {tipo} con prospecto",
        base_legal="Interés legítimo comercial B2B",
        establecimiento_ids=[prospecto_id],
        columnas_tocadas=["contacto_persona"] if contacto_persona else None,
    )
    db.commit()

    return RedirectResponse(
        f"/prospecto/{prospecto_id}?mensaje=Contacto+registrado&mensaje_tipo=ok",
        status_code=status.HTTP_303_SEE_OTHER,
    )


# ============================================================================
# Mapa Leaflet
# ============================================================================
@router.get("/mapa", response_class=HTMLResponse)
def mapa(
    request: Request,
    user: Annotated[Usuario | None, Depends(get_current_user_web)],
):
    if not user:
        return RedirectResponse("/login", status_code=status.HTTP_303_SEE_OTHER)
    return templates.TemplateResponse(
        "mapa.html",
        {
            "request": request,
            "user": user,
            "active": "mapa",
            "canales": list(CANALES),
            "entidades": sorted(ENTIDADES_PRIORIZADAS.items()),
        },
    )


@router.get("/api/mapa-data")
def mapa_data(
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[Usuario | None, Depends(get_current_user_web)],
    canal: str | None = None,
    segmento: str | None = None,
    estado_codigo: str | None = None,
    limit: int = 1000,
) -> JSONResponse:
    if not user:
        raise HTTPException(status_code=401, detail="No autenticado")
    limit = max(100, min(limit, 5000))

    filtros = _filtros_vendedor(user)
    filtros.append(Establecimiento.latitud.is_not(None))
    filtros.append(Establecimiento.longitud.is_not(None))
    if canal:
        filtros.append(Establecimiento.canales.any(canal))
    if segmento:
        filtros.append(Establecimiento.segmento_abc == segmento)
    if estado_codigo:
        filtros.append(Establecimiento.estado_codigo == estado_codigo)

    rows = (
        db.execute(
            select(
                Establecimiento.id,
                Establecimiento.nombre,
                Establecimiento.latitud,
                Establecimiento.longitud,
                Establecimiento.canales,
                Establecimiento.score_prioridad,
                Establecimiento.segmento_abc,
            )
            .where(and_(*filtros))
            .order_by(Establecimiento.score_prioridad.desc().nulls_last())
            .limit(limit)
        )
        .all()
    )

    return JSONResponse({
        "items": [
            {
                "id": r.id,
                "nombre": r.nombre,
                "lat": r.latitud,
                "lon": r.longitud,
                "canales": list(r.canales or []),
                "score": round(r.score_prioridad, 0) if r.score_prioridad is not None else None,
                "segmento_abc": r.segmento_abc,
            }
            for r in rows
        ]
    })
