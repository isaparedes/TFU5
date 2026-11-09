import json
from app.database import SessionLocal
from app import models
from app.settings import settings
from notification_service.common import process_forever, already_processed, mark_processed


def procesar(payload):
    db = SessionLocal()
    try:
        event_id = payload["event_id"]
        if already_processed(db, event_id, "auditoria"):
            return
        if db.query(models.RegistroAuditoria).filter_by(event_id=event_id).first() is None:
            db.add(models.RegistroAuditoria(event_id=event_id, event_type=payload.get("event_type", "desconocido"), solicitud_id=int(payload["solicitud_id"]), payload=json.dumps(payload, ensure_ascii=False)))
        mark_processed(db, event_id, "auditoria")
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


if __name__ == "__main__":
    import socket
    process_forever(settings.REDIS_GROUP_AUDITORIA, "auditoria-" + socket.gethostname(), procesar)
