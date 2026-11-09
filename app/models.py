"""
Modelos SQLAlchemy.

"""
import enum
from datetime import datetime

from sqlalchemy import (
    Column, Integer, String, DateTime, ForeignKey, Enum, Boolean, Text, UniqueConstraint
)
from sqlalchemy.orm import relationship

from app.database import Base


class Rol(str, enum.Enum):
    ADOPTANTE = "adoptante"
    VOLUNTARIO = "voluntario"
    ADMIN = "admin"


class EspecieAnimal(str, enum.Enum):
    PERRO = "perro"
    GATO = "gato"


class EstadoAnimal(str, enum.Enum):
    DISPONIBLE = "disponible"
    RESERVADO = "reservado"
    ALOJADO_TEMPORALMENTE = "alojado_temporalmente"
    ADOPTADO = "adoptado"


class TipoAdopcion(str, enum.Enum):
    DEFINITIVA = "definitiva"
    TEMPORAL = "temporal"


class EstadoSolicitud(str, enum.Enum):
    PENDIENTE = "pendiente"
    APROBADA = "aprobada"
    RECHAZADA = "rechazada"


class Usuario(Base):
    __tablename__ = "usuarios"

    id = Column(Integer, primary_key=True, index=True)
    email = Column(String, unique=True, index=True, nullable=False)
    password_hash = Column(String, nullable=False)
    rol = Column(
        Enum(Rol, name="rol"),
        nullable=False,
        default=Rol.ADOPTANTE
    )
    google_sub = Column(String, unique=True, nullable=True)

    hogar = relationship(
        "HogarTransitorio",
        back_populates="usuario",
        uselist=False
    )


class Animal(Base):
    __tablename__ = "animales"

    id = Column(Integer, primary_key=True, index=True)
    nombre = Column(String, nullable=False)
    especie = Column(
        Enum(EspecieAnimal, name="especieanimal"),
        nullable=False
    )
    estado = Column(
        Enum(EstadoAnimal, name="estadoanimal"),
        nullable=False,
        default=EstadoAnimal.DISPONIBLE
    )
    creado_en = Column(DateTime, default=datetime.utcnow)


class HogarTransitorio(Base):
    __tablename__ = "hogares_transitorios"

    id = Column(Integer, primary_key=True, index=True)

    usuario_email = Column(
        String,
        ForeignKey("usuarios.email"),
        unique=True,
        nullable=False
    )
    responsable = Column(String, nullable=False)
    direccion = Column(String, nullable=False)

    usuario = relationship("Usuario", back_populates="hogar")
    solicitudes = relationship("Solicitud", back_populates="hogar")


class Solicitud(Base):
    __tablename__ = "solicitudes"

    id = Column(Integer, primary_key=True, index=True)

    animal_id = Column(
        Integer,
        ForeignKey("animales.id"),
        nullable=False
    )
    hogar_id = Column(
        Integer,
        ForeignKey("hogares_transitorios.id"),
        nullable=False
    )
    interesado_email = Column(
        String,
        ForeignKey("usuarios.email"),
        nullable=False
    )

    tipo = Column(
        Enum(TipoAdopcion, name="tipoadopcion"),
        nullable=False
    )
    fecha_fin_temporal = Column(DateTime, nullable=True)

    estado = Column(
        Enum(EstadoSolicitud, name="estadosolicitud"),
        nullable=False,
        default=EstadoSolicitud.PENDIENTE
    )
    creada_en = Column(DateTime, default=datetime.utcnow)
    estado_notificacion = Column(String(20), nullable=False, default="pendiente")
    error_notificacion = Column(Text, nullable=True)

    animal = relationship("Animal")
    hogar = relationship("HogarTransitorio", back_populates="solicitudes")


class OutboxEvent(Base):
    __tablename__ = "outbox_events"

    id = Column(Integer, primary_key=True, index=True)
    event_id = Column(String(36), unique=True, nullable=False, index=True)
    event_type = Column(String(100), nullable=False)
    payload = Column(Text, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    published_at = Column(DateTime, nullable=True)


class EventoProcesado(Base):
    __tablename__ = "eventos_procesados"
    __table_args__ = (UniqueConstraint("event_id", "consumer", name="uq_event_consumer"),)

    id = Column(Integer, primary_key=True)
    event_id = Column(String(36), nullable=False, index=True)
    consumer = Column(String(80), nullable=False)
    processed_at = Column(DateTime, default=datetime.utcnow, nullable=False)


class RegistroAuditoria(Base):
    __tablename__ = "registros_auditoria"

    id = Column(Integer, primary_key=True)
    event_id = Column(String(36), unique=True, nullable=False, index=True)
    event_type = Column(String(100), nullable=False)
    solicitud_id = Column(Integer, nullable=False)
    payload = Column(Text, nullable=False)
    registrado_en = Column(DateTime, default=datetime.utcnow, nullable=False)
