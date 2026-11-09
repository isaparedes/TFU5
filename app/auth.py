
"""
Componente Autenticación.
"""
import secrets
from datetime import datetime, timedelta

from authlib.integrations.starlette_client import OAuth
from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.security import HTTPBearer, OAuth2PasswordRequestForm
from jose import JWTError, jwt
from passlib.context import CryptContext
from sqlalchemy.orm import Session

from app.database import get_db
from app import models, schemas
from app.settings import settings

SECRET_KEY = settings.JWT_SECRET # Patrón de facilidad de modificación y despliegue: External Configuration Store
ALGORITHM = settings.JWT_ALGORITHM # Patrón de facilidad de modificación y despliegue: External Configuration Store
ACCESS_TOKEN_EXPIRE_MINUTES = settings.ACCESS_TOKEN_EXPIRE_MINUTES # Patrón de facilidad de modificación y despliegue: External Configuration Store

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
oauth2_scheme = HTTPBearer()

router = APIRouter(prefix="/auth", tags=["Autenticación"])

# Patrón: Federated Identity
oauth = OAuth()
oauth.register(
    name="google",
    client_id=settings.GOOGLE_CLIENT_ID, # Patrón de facilidad de modificación y despliegue: External Configuration Store
    client_secret=settings.GOOGLE_CLIENT_SECRET, # Patrón de facilidad de modificación y despliegue: External Configuration Store
    server_metadata_url=(
        "https://accounts.google.com/.well-known/openid-configuration"
    ),
    client_kwargs={"scope": "openid email profile"},
)


def crear_token(usuario: models.Usuario) -> str:
    payload = {
        "sub": usuario.email,
        "rol": usuario.rol.value,
        "typ": "access",
        "exp": datetime.utcnow()
        + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES),
    }
    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)


def validar_token(credenciales=Depends(oauth2_scheme)) -> dict:
    error = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Credenciales inválidas",
        headers={"WWW-Authenticate": "Bearer"},
    )

    try:
        payload = jwt.decode(
            credenciales.credentials,
            SECRET_KEY,
            algorithms=[ALGORITHM],
        )

        email = payload.get("sub")
        rol = payload.get("rol")

        if not email or not rol or payload.get("typ", "access") != "access":
            raise error

        return {"email": email, "rol": rol}

    except JWTError:
        raise error


def requerir_rol(*roles: models.Rol):
    roles_permitidos = {rol.value for rol in roles}

    def verificar(usuario: dict = Depends(validar_token)) -> dict:
        if usuario.get("rol") not in roles_permitidos:
            raise HTTPException(
                status_code=403,
                detail="No tenés permisos para realizar esta operación",
            )
        return usuario

    return verificar


def requerir_admin(usuario: dict = Depends(validar_token)) -> dict:
    if usuario.get("rol") != models.Rol.ADMIN.value:
        raise HTTPException(status_code=403, detail="Requiere rol admin")
    return usuario


# Patrón: Valet Key
def crear_valet_key(solicitud_id: int, creador_email: str) -> str:
    ahora = datetime.utcnow()
    payload = {
        "sub": creador_email,
        "typ": "valet_key",
        "scope": "solicitud:read",
        "solicitud_id": solicitud_id,
        "iat": ahora,
        "exp": ahora + timedelta(seconds=settings.VALET_TTL), # Patrón de facilidad de modificación y despliegue: External Configuration Store
    }
    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)


def validar_valet_key(token: str, solicitud_id: int) -> dict:
    error = HTTPException(
        status_code=401,
        detail="Valet Key inválida o vencida",
        headers={"WWW-Authenticate": "Bearer"},
    )

    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])

        if (
            payload.get("typ") != "valet_key"
            or payload.get("scope") != "solicitud:read"
            or payload.get("solicitud_id") != solicitud_id
            or not payload.get("sub")
        ):
            raise error

        return payload
    except JWTError:
        raise error


@router.post("/registro", response_model=schemas.Token, status_code=201)
def registrar(datos: schemas.UsuarioCreate, db: Session = Depends(get_db)):
    email = str(datos.email).strip().lower()

    if db.query(models.Usuario).filter_by(email=email).first():
        raise HTTPException(status_code=409, detail="El email ya está registrado")

    usuario = models.Usuario(
        email=email,
        password_hash=pwd_context.hash(datos.password),
        rol=models.Rol.ADOPTANTE,
    )
    db.add(usuario)
    db.commit()
    db.refresh(usuario)

    return schemas.Token(access_token=crear_token(usuario))


@router.post("/login", response_model=schemas.Token)
def login(
    form_data: OAuth2PasswordRequestForm = Depends(),
    db: Session = Depends(get_db),
):
    email = form_data.username.strip().lower()
    usuario = db.query(models.Usuario).filter_by(email=email).first()

    if (
        not usuario
        or not pwd_context.verify(form_data.password, usuario.password_hash)
    ):
        raise HTTPException(status_code=401, detail="Credenciales inválidas")

    return schemas.Token(access_token=crear_token(usuario))


# Patrón: Federated Identity
@router.get("/google/login")
async def login_google(request: Request):
    if not settings.GOOGLE_CLIENT_ID or not settings.GOOGLE_CLIENT_SECRET: # Patrón de facilidad de modificación y despliegue: External Configuration Store
        raise HTTPException(
            status_code=500,
            detail="Faltan las credenciales de Google en la configuración",
        )

    return await oauth.google.authorize_redirect(
        request,
        settings.GOOGLE_REDIRECT_URI, # Patrón de facilidad de modificación y despliegue: External Configuration Store
    )


@router.get("/google/callback", response_model=schemas.Token)
async def callback_google(
    request: Request,
    db: Session = Depends(get_db),
):
    try:
        token_google = await oauth.google.authorize_access_token(request)
    except Exception as exc:
        raise HTTPException(
            status_code=401,
            detail="No se pudo completar la autenticación con Google",
        ) from exc

    usuario_google = token_google.get("userinfo")

    if not usuario_google:
        raise HTTPException(
            status_code=401,
            detail="Google no proporcionó información de identidad válida",
        )

    google_sub = usuario_google.get("sub")
    email = usuario_google.get("email")
    email_verificado = usuario_google.get("email_verified")

    if not google_sub or not email or email_verificado is not True:
        raise HTTPException(
            status_code=401,
            detail="La identidad o el email de Google no están verificados",
        )

    email = email.strip().lower()

    usuario = (
        db.query(models.Usuario)
        .filter_by(google_sub=google_sub)
        .first()
    )

    if usuario is None:
        usuario = db.query(models.Usuario).filter_by(email=email).first()

        if usuario is not None:
            if usuario.google_sub and usuario.google_sub != google_sub:
                raise HTTPException(
                    status_code=409,
                    detail="La cuenta ya está vinculada a otra identidad de Google",
                )
            usuario.google_sub = google_sub
        else:
            usuario = models.Usuario(
                email=email,
                password_hash=pwd_context.hash(secrets.token_urlsafe(32)),
                rol=models.Rol.ADOPTANTE,
                google_sub=google_sub,
            )
            db.add(usuario)

        try:
            db.commit()
            db.refresh(usuario)
        except Exception as exc:
            db.rollback()
            raise HTTPException(
                status_code=500,
                detail="No se pudo guardar el usuario autenticado",
            ) from exc

    return schemas.Token(access_token=crear_token(usuario))
