import json
import logging
import os
import socket
import time
from datetime import datetime

import redis
from sqlalchemy.exc import IntegrityError
from app.database import SessionLocal
from app import models
from app.settings import settings

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("consumers")
r = redis.Redis.from_url(settings.REDIS_STREAM_URL, decode_responses=True)
STREAM = settings.REDIS_STREAM_NAME


def ensure_group(group: str):
    try:
        r.xgroup_create(STREAM, group, id="0-0", mkstream=True)
    except redis.exceptions.ResponseError as exc:
        if "BUSYGROUP" not in str(exc):
            raise


def already_processed(db, event_id, consumer):
    return db.query(models.EventoProcesado).filter_by(event_id=event_id, consumer=consumer).first() is not None


def mark_processed(db, event_id, consumer):
    db.add(models.EventoProcesado(event_id=event_id, consumer=consumer))


def read_events(group, consumer):
    ensure_group(group)
    # Recuperación de mensajes pendientes abandonados por consumidores caídos.
    try:
        claimed = r.xautoclaim(STREAM, group, consumer, min_idle_time=60000, start_id="0-0", count=10)
        entries = claimed[1] if claimed and len(claimed) > 1 else []
        if entries:
            return entries
    except (redis.exceptions.ResponseError, AttributeError):
        pass
    response = r.xreadgroup(group, consumer, {STREAM: ">"}, count=10, block=settings.STREAM_BLOCK_MS)
    return response[0][1] if response else []


def process_forever(group, consumer, handler):
    while True:
        try:
            entries = read_events(group, consumer)
            for message_id, fields in entries:
                try:
                    payload = json.loads(fields.get("payload", "{}"))
                    handler(payload)
                    r.xack(STREAM, group, message_id)
                except Exception:
                    logger.exception("No se pudo procesar mensaje %s; queda pendiente para reintento", message_id)
                    time.sleep(2)
        except Exception:
            logger.exception("Error de consumidor; reintentando")
            time.sleep(3)
