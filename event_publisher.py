"""Publicador Outbox: reintenta publicar eventos confirmados en PostgreSQL."""
import logging
import time
import redis
from datetime import datetime
from app.database import SessionLocal, engine
from app import models
from app.settings import settings

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("outbox-publisher")
client = redis.Redis.from_url(settings.REDIS_STREAM_URL, decode_responses=True)


def asegurar_tabla_outbox():
    """Garantiza que la tabla Outbox exista antes de comenzar a consultar eventos.

    El publicador puede arrancar antes que FastAPI en Docker Compose. Se usa
    el mismo advisory lock que la inicialización de la API para evitar una
    carrera al crear el esquema.
    """
    with engine.begin() as conn:
        conn.execute(__import__("sqlalchemy").text("SELECT pg_advisory_xact_lock(4815162342)"))
        models.OutboxEvent.__table__.create(bind=conn, checkfirst=True)


def publicar_pendientes():
    db = SessionLocal()
    try:
        eventos = db.query(models.OutboxEvent).filter(models.OutboxEvent.published_at.is_(None)).order_by(models.OutboxEvent.id).limit(100).with_for_update(skip_locked=True).all()
        for evento in eventos:
            client.xadd(settings.REDIS_STREAM_NAME, {"event_id": evento.event_id, "event_type": evento.event_type, "payload": evento.payload})
            evento.published_at = datetime.utcnow()
        db.commit()
        return len(eventos)
    except Exception:
        db.rollback()
        logger.exception("No se pudieron publicar eventos Outbox")
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    asegurar_tabla_outbox()
    logger.info("Tabla outbox_events verificada; iniciando publicador")
    while True:
        publicar_pendientes()
        time.sleep(settings.OUTBOX_POLL_SECONDS)
