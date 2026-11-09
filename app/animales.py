
"""Componente Animales."""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app.auth import requerir_rol, validar_token
from app import models, schemas
from app.settings import settings
from app.cache import (
    obtener_cache,
    guardar_cache,
    invalidar_cache_animales,
)

router = APIRouter(prefix="/animales", tags=["Animales"])


def serializar_animal(animal: models.Animal) -> dict:
    return schemas.AnimalOut.model_validate(
        animal,
        from_attributes=True,
    ).model_dump(mode="json")


@router.post("", response_model=schemas.AnimalOut, status_code=201)
def crear_animal(
    datos: schemas.AnimalCreate,
    db: Session = Depends(get_db),
    _usuario: dict = Depends(
        requerir_rol(models.Rol.ADMIN, models.Rol.VOLUNTARIO)
    ),
):
    animal = models.Animal(
        nombre=datos.nombre,
        especie=datos.especie,
        estado=models.EstadoAnimal.DISPONIBLE,
    )

    db.add(animal)
    db.commit()
    db.refresh(animal)

    # Patrón de rendimiento: Caché-Aside
    invalidar_cache_animales()
    return animal


@router.get("", response_model=list[schemas.AnimalOut])
def listar_animales_disponibles(
    db: Session = Depends(get_db),
    _usuario: dict = Depends(validar_token),
):
    clave = "animales:disponibles"
    datos = obtener_cache(clave)

    if datos is not None:
        return datos

    animales = (
        db.query(models.Animal)
        .filter(
            models.Animal.estado == models.EstadoAnimal.DISPONIBLE
        )
        .all()
    )

    resultado = [serializar_animal(animal) for animal in animales]

    # Patrón de rendimiento: Caché-Aside
    guardar_cache(clave, resultado, ttl=settings.CACHE_TTL_LISTA) # Patrón de facilidad de modificación y despliegue: External Configuration Store

    return resultado


@router.get("/todos", response_model=list[schemas.AnimalOut])
def listar_todos_los_animales(
    db: Session = Depends(get_db),
    _usuario: dict = Depends(
        requerir_rol(models.Rol.ADMIN, models.Rol.VOLUNTARIO)
    ),
):
    return db.query(models.Animal).all()


@router.get("/{animal_id}", response_model=schemas.AnimalOut)
def obtener_animal(
    animal_id: int,
    db: Session = Depends(get_db),
    usuario: dict = Depends(validar_token),
):
    clave = f"animal:{animal_id}"
    datos = obtener_cache(clave)

    if datos is not None:
        if (
            usuario["rol"] == models.Rol.ADOPTANTE.value
            and datos["estado"] != models.EstadoAnimal.DISPONIBLE.value
        ):
            raise HTTPException(status_code=404, detail="Animal no encontrado")
        return datos

    animal = db.get(models.Animal, animal_id)

    if animal is None:
        raise HTTPException(status_code=404, detail="Animal no encontrado")

    if (
        usuario["rol"] == models.Rol.ADOPTANTE.value
        and animal.estado != models.EstadoAnimal.DISPONIBLE
    ):
        raise HTTPException(status_code=404, detail="Animal no encontrado")

    resultado = serializar_animal(animal)

    # Patrón de rendimiento: Caché-Aside
    guardar_cache(clave, resultado, ttl=settings.CACHE_TTL_DETALLE) # Patrón de facilidad de modificación y despliegue: External Configuration Store

    return resultado
