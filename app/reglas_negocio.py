
"""Reglas de negocio compartidas por los endpoints REST."""

from datetime import datetime

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app import models


def liberar_temporales_vencidos(db: Session) -> None:
    ahora = datetime.utcnow()

    solicitudes = (
        db.query(models.Solicitud)
        .filter(
            models.Solicitud.estado == models.EstadoSolicitud.APROBADA,
            models.Solicitud.tipo == models.TipoAdopcion.TEMPORAL,
            models.Solicitud.fecha_fin_temporal <= ahora,
        )
        .all()
    )

    for solicitud in solicitudes:
        animal = db.get(models.Animal, solicitud.animal_id)

        if (
            animal
            and animal.estado == models.EstadoAnimal.ALOJADO_TEMPORALMENTE
        ):
            animal.estado = models.EstadoAnimal.DISPONIBLE


def validar_usuario_puede_solicitar(
    db: Session,
    email: str,
    animal_id: int,
) -> tuple[models.Usuario, models.HogarTransitorio, models.Animal]:
    usuario = (
        db.query(models.Usuario)
        .filter_by(email=email)
        .first()
    )

    if usuario is None:
        raise HTTPException(status_code=401, detail="Usuario no encontrado")

    hogar = (
        db.query(models.HogarTransitorio)
        .filter_by(usuario_email=email)
        .first()
    )

    if hogar is None:
        raise HTTPException(
            status_code=409,
            detail="Primero tenés que registrar los datos de tu hogar",
        )

    animal = db.get(models.Animal, animal_id)

    if animal is None:
        raise HTTPException(status_code=404, detail="Animal no encontrado")

    if animal.estado != models.EstadoAnimal.DISPONIBLE:
        raise HTTPException(
            status_code=409,
            detail="El animal no está disponible para adopción",
        )

    pendiente = (
        db.query(models.Solicitud)
        .filter(
            models.Solicitud.interesado_email == email,
            models.Solicitud.estado == models.EstadoSolicitud.PENDIENTE,
        )
        .first()
    )

    if pendiente:
        raise HTTPException(
            status_code=409,
            detail="Ya tenés una solicitud pendiente de resolución",
        )

    hogar_ocupado = (
        db.query(models.Solicitud)
        .join(models.Animal, models.Solicitud.animal_id == models.Animal.id)
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
            detail="Tu hogar ya tiene un animal alojado",
        )

    return usuario, hogar, animal
