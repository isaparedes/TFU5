"""
Configuración de la base de datos (PostgreSQL).

"""
from app.settings import settings
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base

DATABASE_URL = settings.DATABASE_URL # Patrón de facilidad de modificación y despliegue: External Configuration Store

engine = create_engine(DATABASE_URL, pool_pre_ping=True)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


def get_db():
    """Dependencia de FastAPI: una sesión por request, sin estado entre requests."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()



