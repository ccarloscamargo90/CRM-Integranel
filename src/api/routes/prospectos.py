"""Endpoints de prospectos — listado filtrable, detalle, registro de contacto."""

from __future__ import annotations

from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy import and_, func, select
from sqlalchemy.orm import Session

from src.api.dependencies import get_db, require_role
from src.compliance.lfpdppp import registrar_operacion
from src.core.models import EnriquecimientoGoogle, Establecimiento, Interaccion, Usuario

router = APIRouter(prefix="/prospectos", tags=["prospectos"])


class ProspectoOut(BaseModel):
    id: int
    nombre: str
    razon_social: str | None = None
    scian_codigo: str
    canales: list[str]
    estado: str | None = None
    estado_codigo: str | None = None
    municipio: str | None = None
    direccion: str | None = None
    telefono: str | None = None
    email: str | None = None
    sitio_web: str | None = None
    latitud: float | None = None
    longitud: float | None = None
    score_prioridad: float | None = None
    segmento_abc: str | None = None
    estado_pipeline: str
    riesgo_69b: bool
    google_rating: float | None = None
    google_user_rating_count: int | None = None
    cadena_id: int | None = None
    etiquetas: list[str] = []


class ProspectoListadoOut(BaseModel):
    total: int
    items: list[ProspectoOut]


class ContactoIn(BaseModel):
    tipo: Literal["visita", "llamada", "email", "whatsapp", "cotizacion", "pedido", "muestra", "seguimiento"]
    canal_contacto: str | None = None
    resultado: str | None = None
    siguiente_paso: str | None = None
    contacto_persona: str | None = None
    notas: str | None = None
    nuevo_estado_pipeline: str | None = None


@router.get("", response_model=ProspectoListadoOut)
def listar_prospectos(
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[Usuario, Depends(require_role("admin", "vendedor", "jefe"))],
    canal: str | None = Query(None, description="Filtra por canal: Tortillerias / AlimentoBalanceado / ..."),
    segmento: str | None = Query(None, pattern="^[ABCX]$"),
    estado_pipeline: str | None = None,
    estado_codigo: str | None = None,
    score_min: float | None = None,
    riesgo_69b: bool | None = None,
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
) -> ProspectoListadoOut:
    """Listado paginado con filtros. Vendedor solo ve sus propios prospectos."""
    filtros = []
    if canal:
        filtros.append(Establecimiento.canales.any(canal))
    if segmento:
        filtros.append(Establecimiento.segmento_abc == segmento)
    if estado_pipeline:
        filtros.append(Establecimiento.estado_pipeline == estado_pipeline)
    if estado_codigo:
        filtros.append(Establecimiento.estado_codigo == estado_codigo)
    if score_min is not None:
        filtros.append(Establecimiento.score_prioridad >= score_min)
    if riesgo_69b is not None:
        filtros.append(Establecimiento.riesgo_69b == riesgo_69b)

    # Vendedor ve solo sus prospectos asignados
    if user.rol == "vendedor" and user.vendedor_id:
        filtros.append(Establecimiento.vendedor_id == user.vendedor_id)

    where = and_(*filtros) if filtros else None
    base_query = select(Establecimiento)
    if where is not None:
        base_query = base_query.where(where)

    total = db.execute(
        select(func.count()).select_from(Establecimiento).where(where) if where is not None
        else select(func.count()).select_from(Establecimiento)
    ).scalar_one()

    rows = db.execute(
        base_query.order_by(Establecimiento.score_prioridad.desc().nulls_last())
        .limit(limit)
        .offset(offset)
    ).scalars().all()

    # Recolectar enriquecimientos Google en una sola consulta
    ids = [e.id for e in rows]
    enriqs = {
        eg.establecimiento_id: eg
        for eg in db.execute(
            select(EnriquecimientoGoogle).where(EnriquecimientoGoogle.establecimiento_id.in_(ids))
        ).scalars().all()
    } if ids else {}

    items = []
    for e in rows:
        eg = enriqs.get(e.id)
        items.append(
            ProspectoOut(
                id=e.id,
                nombre=e.nombre,
                razon_social=e.razon_social,
                scian_codigo=e.scian_codigo,
                canales=list(e.canales or []),
                estado=e.estado,
                estado_codigo=e.estado_codigo,
                municipio=e.municipio,
                direccion=e.direccion,
                telefono=e.telefono,
                email=e.email,
                sitio_web=e.sitio_web,
                latitud=e.latitud,
                longitud=e.longitud,
                score_prioridad=e.score_prioridad,
                segmento_abc=e.segmento_abc,
                estado_pipeline=e.estado_pipeline,
                riesgo_69b=e.riesgo_69b,
                google_rating=eg.google_rating if eg and eg.match_status == "match" else None,
                google_user_rating_count=eg.google_user_rating_count if eg and eg.match_status == "match" else None,
                cadena_id=e.cadena_id,
                etiquetas=list(e.etiquetas or []),
            )
        )

    return ProspectoListadoOut(total=total, items=items)


@router.get("/{prospecto_id}", response_model=ProspectoOut)
def detalle_prospecto(
    prospecto_id: int,
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[Usuario, Depends(require_role("admin", "vendedor", "jefe"))],
) -> ProspectoOut:
    e = db.get(Establecimiento, prospecto_id)
    if not e:
        raise HTTPException(status_code=404, detail="Prospecto no existe")

    # Vendedor solo accede a los suyos
    if user.rol == "vendedor" and user.vendedor_id and e.vendedor_id != user.vendedor_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Prospecto no asignado a ti")

    eg = db.get(EnriquecimientoGoogle, prospecto_id)

    # Compliance log: el detalle incluye PII (telefono, email, contacto_*)
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

    return ProspectoOut(
        id=e.id,
        nombre=e.nombre,
        razon_social=e.razon_social,
        scian_codigo=e.scian_codigo,
        canales=list(e.canales or []),
        estado=e.estado,
        estado_codigo=e.estado_codigo,
        municipio=e.municipio,
        direccion=e.direccion,
        telefono=e.telefono,
        email=e.email,
        sitio_web=e.sitio_web,
        latitud=e.latitud,
        longitud=e.longitud,
        score_prioridad=e.score_prioridad,
        segmento_abc=e.segmento_abc,
        estado_pipeline=e.estado_pipeline,
        riesgo_69b=e.riesgo_69b,
        google_rating=eg.google_rating if eg and eg.match_status == "match" else None,
        google_user_rating_count=eg.google_user_rating_count if eg and eg.match_status == "match" else None,
        cadena_id=e.cadena_id,
        etiquetas=list(e.etiquetas or []),
    )


@router.post("/{prospecto_id}/contacto", status_code=201)
def registrar_contacto(
    prospecto_id: int,
    body: ContactoIn,
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[Usuario, Depends(require_role("admin", "vendedor"))],
) -> dict:
    """Registra una interacción comercial. Opcionalmente cambia estado_pipeline."""
    e = db.get(Establecimiento, prospecto_id)
    if not e:
        raise HTTPException(status_code=404, detail="Prospecto no existe")
    if user.rol == "vendedor" and user.vendedor_id and e.vendedor_id != user.vendedor_id:
        raise HTTPException(status_code=403, detail="Prospecto no asignado a ti")

    interaccion = Interaccion(
        establecimiento_id=prospecto_id,
        vendedor_id=user.vendedor_id,
        usuario_id=user.id,
        tipo=body.tipo,
        canal_contacto=body.canal_contacto,
        resultado=body.resultado,
        siguiente_paso=body.siguiente_paso,
        contacto_persona=body.contacto_persona,
        notas=body.notas,
    )
    db.add(interaccion)
    db.flush()

    # Cambio de estado_pipeline (si pidió)
    if body.nuevo_estado_pipeline and body.nuevo_estado_pipeline != e.estado_pipeline:
        from src.core.models import PipelineEtapaHistorial

        db.add(
            PipelineEtapaHistorial(
                establecimiento_id=prospecto_id,
                usuario_id=user.id,
                etapa_anterior=e.estado_pipeline,
                etapa_nueva=body.nuevo_estado_pipeline,
                motivo=f"Tras interacción {body.tipo}",
            )
        )
        e.estado_pipeline = body.nuevo_estado_pipeline

    # Compliance log
    registrar_operacion(
        session=db,
        usuario_id=user.id,
        tipo_operacion="contacto_comercial",
        finalidad=f"Registro de {body.tipo} con prospecto",
        base_legal="Interés legítimo comercial B2B",
        establecimiento_ids=[prospecto_id],
        columnas_tocadas=["contacto_persona"] if body.contacto_persona else None,
    )
    db.commit()

    return {"interaccion_id": interaccion.id, "estado_pipeline": e.estado_pipeline}
