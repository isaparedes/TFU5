from fastapi import FastAPI, HTTPException, Depends
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from redis.exceptions import RedisError
from starlette.middleware.sessions import SessionMiddleware
from app.cache import redis_client
from app.database import Base, engine
from app import models, auth, animales, hogares, adopciones
from app.auth import requerir_admin
from app.settings import settings

app = FastAPI(title="TFU5 - Refugio de animales", description="API REST con Redis Streams, consumidores independientes, Outbox y servicio SOAP.", version="2.0.0")
app.add_middleware(SessionMiddleware, secret_key=settings.SESSION_SECRET, same_site="lax", https_only=False)


@app.on_event("startup")
def crear_tablas_y_compatibilidad():
    with engine.begin() as conn:
        conn.execute(text("SELECT pg_advisory_xact_lock(4815162342)"))
        Base.metadata.create_all(bind=conn)
        conn.execute(text("ALTER TABLE solicitudes ADD COLUMN IF NOT EXISTS estado_notificacion VARCHAR(20) NOT NULL DEFAULT 'pendiente'"))
        conn.execute(text("ALTER TABLE solicitudes ADD COLUMN IF NOT EXISTS error_notificacion TEXT"))


@app.get("/api-health", dependencies=[Depends(requerir_admin)])
def api_health():
    import socket
    return {"status": "healthy", "instance": socket.gethostname()}


@app.get("/db-health", dependencies=[Depends(requerir_admin)])
def db_health():
    try:
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
        return {"status": "healthy", "database": "connected"}
    except SQLAlchemyError:
        raise HTTPException(status_code=503, detail={"status": "unhealthy", "database": "disconnected"})


@app.get("/redis-health", dependencies=[Depends(requerir_admin)])
def redis_health():
    try:
        redis_client.ping()
        return {"status": "healthy", "redis": "connected"}
    except RedisError:
        raise HTTPException(status_code=503, detail={"status": "unhealthy", "redis": "disconnected"})


app.include_router(auth.router)
app.include_router(animales.router)
app.include_router(hogares.router)
app.include_router(adopciones.router)
