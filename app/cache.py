# Patrón de rendimiento: Caché-Aside
import json

import redis
from redis.exceptions import RedisError
from app.settings import settings

redis_client = redis.Redis.from_url(
    settings.REDIS_URL, # Patrón de facilidad de modificación y despliegue: External Configuration Store
    decode_responses=True,
)


def obtener_cache(clave: str):
    try:
        dato = redis_client.get(clave)
        return json.loads(dato) if dato is not None else None
    except (RedisError, ValueError):
        return None


def guardar_cache(clave: str, datos, ttl: int = 60):
    try:
        redis_client.set(clave, json.dumps(datos), ex=ttl)
    except RedisError:
        pass

def invalidar_cache_animales(animal_id: int | None = None):
    claves = ["animales:list", "animales:disponibles"]

    if animal_id is not None:
        claves.append(f"animal:{animal_id}")

    try:
        redis_client.delete(*claves)
    except RedisError:
        pass


