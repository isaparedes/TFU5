"""
Esquemas Pydantic de la API REST.

"""

from datetime import datetime
from pydantic import BaseModel, EmailStr, model_validator
from datetime import datetime, timezone

from app.models import (
    Rol,
    EspecieAnimal,
    EstadoAnimal,
    EstadoSolicitud,
    TipoAdopcion,
)


class UsuarioCreate(BaseModel):
    email: EmailStr
    password: str


class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"


class AnimalCreate(BaseModel):
    nombre: str
    especie: EspecieAnimal


class AnimalOut(BaseModel):
    id: int
    nombre: str
    especie: EspecieAnimal
    estado: EstadoAnimal

    class Config:
        from_attributes = True


class HogarCreate(BaseModel):
    responsable: str
    direccion: str


class HogarOut(BaseModel):
    id: int
    usuario_email: EmailStr
    responsable: str
    direccion: str

    class Config:
        from_attributes = True


class SolicitudCreate(BaseModel):
    animal_id: int
    tipo: TipoAdopcion
    fecha_fin_temporal: datetime | None = None

    @model_validator(mode="after")
    def validar_fechas(self):
        fecha = self.fecha_fin_temporal

        if fecha is not None and fecha.tzinfo is not None:
            self.fecha_fin_temporal = (
                fecha.astimezone(timezone.utc).replace(tzinfo=None)
            )

        if self.tipo == TipoAdopcion.TEMPORAL:
            if self.fecha_fin_temporal is None:
                raise ValueError(
                    "Una solicitud temporal requiere fecha de finalización"
                )

            if self.fecha_fin_temporal <= datetime.utcnow():
                raise ValueError(
                    "La fecha de finalización debe estar en el futuro"
                )

        elif self.fecha_fin_temporal is not None:
            raise ValueError(
                "Una solicitud definitiva no debe tener fecha de finalización"
            )

        return self


class SolicitudOut(BaseModel):
    id: int
    animal_id: int
    hogar_id: int
    interesado_email: EmailStr
    tipo: TipoAdopcion
    fecha_fin_temporal: datetime | None
    estado: EstadoSolicitud
    estado_notificacion: str = "pendiente"

    class Config:
        from_attributes = True

# Patrón de seguridad: Valet Key
class SolicitudCompartidaOut(BaseModel):
    id: int
    animal_id: int
    tipo: TipoAdopcion
    fecha_fin_temporal: datetime | None
    estado: EstadoSolicitud

    class Config:
        from_attributes = True

class SolicitudRegistrada(BaseModel):
    solicitud_id: int
    estado: str = "registrada"
    estado_notificacion: str = "pendiente"
    mensaje: str


class EstadoNotificacion(BaseModel):
    solicitud_id: int
    estado_notificacion: str
    error: str | None = None
