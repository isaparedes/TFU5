import json
import uuid
from datetime import datetime
from fastapi import HTTPException
from sqlalchemy.orm import Session
from app import models
from app.reglas_negocio import liberar_temporales_vencidos, validar_usuario_puede_solicitar


def registrar_solicitud(db: Session, datos, interesado_email: str):
    try:
        liberar_temporales_vencidos(db)
        usuario, hogar, animal = validar_usuario_puede_solicitar(db, interesado_email, datos.animal_id)
        # Bloqueos para reducir carreras entre solicitudes concurrentes.
        db.query(models.Animal).filter_by(id=animal.id).with_for_update().first()
        db.query(models.Usuario).filter_by(email=interesado_email).with_for_update().first()
        # Revalidar disponibilidad luego de adquirir el bloqueo.
        db.refresh(animal)
        if animal.estado != models.EstadoAnimal.DISPONIBLE:
            raise HTTPException(status_code=409, detail="El animal no está disponible para adopción")
        pendiente = db.query(models.Solicitud).filter_by(interesado_email=interesado_email, estado=models.EstadoSolicitud.PENDIENTE).first()
        if pendiente:
            raise HTTPException(status_code=409, detail="Ya tenés una solicitud pendiente de resolución")
        solicitud = models.Solicitud(animal_id=animal.id, hogar_id=hogar.id, interesado_email=interesado_email, tipo=datos.tipo, fecha_fin_temporal=datos.fecha_fin_temporal, estado=models.EstadoSolicitud.PENDIENTE, estado_notificacion="pendiente")
        db.add(solicitud)
        db.flush()
        event_id = str(uuid.uuid4())
        payload = {"event_id": event_id, "event_type": "SolicitudRegistrada", "version": 1, "solicitud_id": solicitud.id, "interesado_email": interesado_email, "animal_id": animal.id, "created_at": datetime.utcnow().isoformat()}
        db.add(models.OutboxEvent(event_id=event_id, event_type="SolicitudRegistrada", payload=json.dumps(payload, ensure_ascii=False)))
        db.commit()
        db.refresh(solicitud)
        return solicitud
    except HTTPException:
        db.rollback(); raise
    except Exception:
        db.rollback(); raise
