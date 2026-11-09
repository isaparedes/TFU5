
"""Componente Hogares."""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app.auth import validar_token, requerir_rol
from app import models, schemas

router = APIRouter(prefix="/hogares", tags=["Hogares"])


@router.post("", response_model=schemas.HogarOut, status_code=201)
def crear_hogar(
    datos: schemas.HogarCreate,
    db: Session = Depends(get_db),
    usuario: dict = Depends(requerir_rol(models.Rol.ADOPTANTE)),
):
    existente = (
        db.query(models.HogarTransitorio)
        .filter_by(usuario_email=usuario["email"])
        .first()
    )

    if existente:
        raise HTTPException(
            status_code=409,
            detail="Ya tenés un hogar registrado",
        )

    hogar = models.HogarTransitorio(
        usuario_email=usuario["email"],
        responsable=datos.responsable,
        direccion=datos.direccion,
    )

    db.add(hogar)
    db.commit()
    db.refresh(hogar)
    return hogar


@router.get("/mi-hogar", response_model=schemas.HogarOut)
def obtener_mi_hogar(
    db: Session = Depends(get_db),
    usuario: dict = Depends(requerir_rol(models.Rol.ADOPTANTE)),
):
    hogar = (
        db.query(models.HogarTransitorio)
        .filter_by(usuario_email=usuario["email"])
        .first()
    )

    if hogar is None:
        raise HTTPException(
            status_code=404,
            detail="Todavía no registraste tu hogar",
        )

    return hogar


@router.get("", response_model=list[schemas.HogarOut])
def listar_hogares(
    db: Session = Depends(get_db),
    _usuario: dict = Depends(
        requerir_rol(models.Rol.ADMIN, models.Rol.VOLUNTARIO)
    ),
):
    return db.query(models.HogarTransitorio).all()
