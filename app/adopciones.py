"""Endpoints REST para solicitudes de adopción."""
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.orm import Session
from app.database import get_db
from app.auth import validar_token, requerir_rol, crear_valet_key, validar_valet_key
from app import models, schemas
from app.cache import invalidar_cache_animales
from app.settings import settings
from app.reglas_negocio import liberar_temporales_vencidos
from app.services.solicitudes import registrar_solicitud

router = APIRouter(prefix="/adopciones", tags=["Adopciones"])
valet_bearer = HTTPBearer()


@router.post("", response_model=schemas.SolicitudRegistrada, status_code=status.HTTP_201_CREATED)
def crear_solicitud(datos: schemas.SolicitudCreate, db: Session = Depends(get_db), usuario: dict = Depends(requerir_rol(models.Rol.ADOPTANTE))):
    solicitud = registrar_solicitud(db, datos, usuario["email"])
    invalidar_cache_animales(solicitud.animal_id)
    return {"solicitud_id": solicitud.id, "estado": "registrada", "estado_notificacion": solicitud.estado_notificacion, "mensaje": "Solicitud registrada. La notificación se procesará en segundo plano."}


@router.get("", response_model=list[schemas.SolicitudOut])
def listar_solicitudes(estado: models.EstadoSolicitud | None = Query(default=None), db: Session = Depends(get_db), usuario: dict = Depends(validar_token)):
    consulta = db.query(models.Solicitud)
    if usuario["rol"] == models.Rol.ADOPTANTE.value:
        consulta = consulta.filter(models.Solicitud.interesado_email == usuario["email"])
    elif usuario["rol"] not in (models.Rol.ADMIN.value, models.Rol.VOLUNTARIO.value):
        raise HTTPException(status_code=403, detail="No tenés permiso")
    if estado is not None:
        consulta = consulta.filter(models.Solicitud.estado == estado)
    return consulta.order_by(models.Solicitud.creada_en.desc()).all()


@router.get("/{solicitud_id}/estado-notificacion", response_model=schemas.EstadoNotificacion)
def consultar_estado_notificacion(solicitud_id: int, db: Session = Depends(get_db), usuario: dict = Depends(validar_token)):
    solicitud = db.get(models.Solicitud, solicitud_id)
    if solicitud is None:
        raise HTTPException(status_code=404, detail="Solicitud no encontrada")
    es_staff = usuario["rol"] in (models.Rol.ADMIN.value, models.Rol.VOLUNTARIO.value)
    if not es_staff and solicitud.interesado_email != usuario["email"]:
        raise HTTPException(status_code=403, detail="No tenés permiso")
    return {"solicitud_id": solicitud.id, "estado_notificacion": solicitud.estado_notificacion, "error": solicitud.error_notificacion}


@router.post(
    "/{solicitud_id}/aprobar",
    response_model=schemas.SolicitudOut,
)
def aprobar_solicitud(
    solicitud_id: int,
    db: Session = Depends(get_db),
    _usuario: dict = Depends(requerir_rol(models.Rol.ADMIN)),
):
    try:
        referencia = db.get(models.Solicitud, solicitud_id)

        if referencia is None:
            raise HTTPException(status_code=404, detail="Solicitud no encontrada")

        usuario_solicitante = (
            db.query(models.Usuario)
            .filter_by(email=referencia.interesado_email)
            .with_for_update()
            .first()
        )

        hogar = (
            db.query(models.HogarTransitorio)
            .filter_by(id=referencia.hogar_id)
            .with_for_update()
            .first()
        )

        animal = (
            db.query(models.Animal)
            .filter_by(id=referencia.animal_id)
            .with_for_update()
            .first()
        )

        solicitud = (
            db.query(models.Solicitud)
            .filter_by(id=solicitud_id)
            .with_for_update()
            .first()
        )

        if (
            usuario_solicitante is None
            or hogar is None
            or animal is None
            or solicitud is None
        ):
            raise HTTPException(
                status_code=404,
                detail="No se encontraron todos los datos de la solicitud",
            )

        liberar_temporales_vencidos(db)
        db.flush()

        if solicitud.estado != models.EstadoSolicitud.PENDIENTE:
            raise HTTPException(
                status_code=409,
                detail="La solicitud ya fue procesada",
            )

        if animal.estado != models.EstadoAnimal.DISPONIBLE:
            raise HTTPException(
                status_code=409,
                detail="El animal ya no está disponible",
            )

        otra_solicitud_pendiente = (
            db.query(models.Solicitud)
            .filter(
                models.Solicitud.interesado_email == solicitud.interesado_email,
                models.Solicitud.estado == models.EstadoSolicitud.PENDIENTE,
                models.Solicitud.id != solicitud.id,
            )
            .first()
        )

        if otra_solicitud_pendiente:
            raise HTTPException(
                status_code=409,
                detail="El solicitante tiene otra solicitud pendiente",
            )

        hogar_ocupado = (
            db.query(models.Solicitud)
            .join(
                models.Animal,
                models.Solicitud.animal_id == models.Animal.id,
            )
            .filter(
                models.Solicitud.hogar_id == hogar.id,
                models.Solicitud.estado == models.EstadoSolicitud.APROBADA,
                models.Animal.estado.in_([
                    models.EstadoAnimal.ADOPTADO,
                    models.EstadoAnimal.ALOJADO_TEMPORALMENTE,
                ]),
            )
            .first()
        )

        if hogar_ocupado:
            raise HTTPException(
                status_code=409,
                detail="El hogar ya tiene un animal alojado",
            )

        if solicitud.tipo == models.TipoAdopcion.DEFINITIVA:
            animal.estado = models.EstadoAnimal.ADOPTADO
        else:
            if (
                solicitud.fecha_fin_temporal is None
                or solicitud.fecha_fin_temporal <= datetime.utcnow()
            ):
                raise HTTPException(
                    status_code=409,
                    detail="La fecha de finalización temporal ya venció",
                )
            animal.estado = models.EstadoAnimal.ALOJADO_TEMPORALMENTE

        solicitud.estado = models.EstadoSolicitud.APROBADA

        (
            db.query(models.Solicitud)
            .filter(
                models.Solicitud.animal_id == animal.id,
                models.Solicitud.id != solicitud.id,
                models.Solicitud.estado == models.EstadoSolicitud.PENDIENTE,
            )
            .update(
                {"estado": models.EstadoSolicitud.RECHAZADA},
                synchronize_session=False,
            )
        )

        db.commit()
        db.refresh(solicitud)

    except HTTPException:
        db.rollback()
        raise
    except Exception:
        db.rollback()
        raise

    # Patrón de rendimiento: Caché-Aside
    invalidar_cache_animales(animal.id)
    return solicitud


@router.post(
    "/{solicitud_id}/rechazar",
    response_model=schemas.SolicitudOut,
)
def rechazar_solicitud(
    solicitud_id: int,
    db: Session = Depends(get_db),
    _usuario: dict = Depends(requerir_rol(models.Rol.ADMIN)),
):
    solicitud = (
        db.query(models.Solicitud)
        .filter_by(id=solicitud_id)
        .with_for_update()
        .first()
    )

    if solicitud is None:
        raise HTTPException(status_code=404, detail="Solicitud no encontrada")

    if solicitud.estado != models.EstadoSolicitud.PENDIENTE:
        raise HTTPException(
            status_code=409,
            detail="La solicitud ya fue procesada",
        )

    solicitud.estado = models.EstadoSolicitud.RECHAZADA
    db.commit()
    db.refresh(solicitud)

    return solicitud


# Patrón de seguridad: Valet Key
@router.post("/{solicitud_id}/valet-key")
def generar_valet_key(
    solicitud_id: int,
    db: Session = Depends(get_db),
    usuario: dict = Depends(requerir_rol(models.Rol.ADMIN)),
):
    solicitud = db.get(models.Solicitud, solicitud_id)

    if solicitud is None:
        raise HTTPException(status_code=404, detail="Solicitud no encontrada")

    return {
        "valet_key": crear_valet_key(
            solicitud_id=solicitud_id,
            creador_email=usuario["email"],
        ),
        "tipo": "solicitud:read",
        "solicitud_id": solicitud_id,
        "expira_en_segundos": settings.VALET_TTL, # Patrón de facilidad de modificación y despliegue: External Configuration Store
    }

# Patrón de seguridad: Valet Key
@router.get(
    "/compartida/{solicitud_id}",
    response_model=schemas.SolicitudCompartidaOut,
)
def consultar_solicitud_compartida(
    solicitud_id: int,
    credenciales: HTTPAuthorizationCredentials = Depends(valet_bearer),
    db: Session = Depends(get_db),
):
    validar_valet_key(
        token=credenciales.credentials,
        solicitud_id=solicitud_id,
    )

    solicitud = db.get(models.Solicitud, solicitud_id)

    if solicitud is None:
        raise HTTPException(status_code=404, detail="Solicitud no encontrada")

    return solicitud
