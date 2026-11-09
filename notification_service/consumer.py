import logging
from zeep import Client
from zeep.transports import Transport
import requests
from app.database import SessionLocal
from app import models
from app.settings import settings
from notification_service.common import process_forever, already_processed, mark_processed, logger
from notification_service.circuit_breaker import CircuitBreaker

breaker = CircuitBreaker(settings.CIRCUIT_BREAKER_FAILURES, settings.CIRCUIT_BREAKER_RESET_SECONDS)


def consultar_solicitud_soap(solicitud_id):
    session = requests.Session()
    transport = Transport(session=session, timeout=settings.SOAP_TIMEOUT)
    client = Client(settings.SOAP_URL, transport=transport)
    respuesta = client.service.ConsultarSolicitud(int(solicitud_id))
    if not respuesta.encontrada:
        raise ValueError(respuesta.error or "Solicitud no encontrada en SOAP")
    return {
        "solicitud_id": respuesta.solicitud_id,
        "interesado_email": respuesta.interesado_email,
        "animal_id": respuesta.animal_id,
        "animal_nombre": respuesta.animal_nombre,
        "tipo": respuesta.tipo,
        "estado": respuesta.estado,
    }


def procesar(payload):
    event_id = payload["event_id"]
    solicitud_id = int(payload["solicitud_id"])
    db = SessionLocal()
    try:
        if already_processed(db, event_id, "notificaciones"):
            return
        # El Circuit Breaker protege exclusivamente la llamada al servicio SOAP.
        detalle = breaker.call(consultar_solicitud_soap, solicitud_id)
        # Notificación de demostración: se registra en logs. No simula un email real.
        logger.info("NOTIFICACION DEMO: solicitud=%s email=%s animal=%s estado=%s", solicitud_id, detalle["interesado_email"], detalle["animal_nombre"], detalle["estado"])
        solicitud = db.get(models.Solicitud, solicitud_id)
        if solicitud is None:
            raise ValueError("La solicitud consultada por SOAP ya no existe")
        solicitud.estado_notificacion = "enviada"
        solicitud.error_notificacion = None
        mark_processed(db, event_id, "notificaciones")
        db.commit()
    except Exception as exc:
        db.rollback()
        try:
            solicitud = db.get(models.Solicitud, solicitud_id)
            if solicitud:
                solicitud.estado_notificacion = "fallida"
                solicitud.error_notificacion = str(exc)[:1000]
                db.commit()
        except Exception:
            db.rollback()
        raise
    finally:
        db.close()


if __name__ == "__main__":
    process_forever(settings.REDIS_GROUP_NOTIFICACIONES, "notificaciones-" + __import__("socket").gethostname(), procesar)
