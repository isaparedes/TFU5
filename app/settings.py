from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    SESSION_SECRET: str = "dev-session-secret-change-me"
    JWT_SECRET: str = "dev-jwt-secret-change-me"
    GOOGLE_CLIENT_ID: str = ""
    GOOGLE_CLIENT_SECRET: str = ""
    GOOGLE_REDIRECT_URI: str = "http://localhost:8000/auth/google/callback"
    DATABASE_URL: str = "postgresql://tfu4:tfu4@db:5432/tfu4"
    REDIS_URL: str = "redis://redis:6379/0"
    REDIS_STREAM_URL: str = "redis://redis:6379/2"
    REDIS_STREAM_NAME: str = "solicitudes"
    REDIS_GROUP_NOTIFICACIONES: str = "grupo_notificaciones"
    REDIS_GROUP_AUDITORIA: str = "grupo_auditoria"
    SOAP_URL: str = "http://soap:8001/?wsdl"
    SOAP_TIMEOUT: int = 5
    STREAM_BLOCK_MS: int = 5000
    OUTBOX_POLL_SECONDS: int = 2
    CIRCUIT_BREAKER_FAILURES: int = 3
    CIRCUIT_BREAKER_RESET_SECONDS: int = 30
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60
    CACHE_TTL_LISTA: int = 30
    CACHE_TTL_DETALLE: int = 60
    VALET_TTL: int = 300

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")


settings = Settings()
