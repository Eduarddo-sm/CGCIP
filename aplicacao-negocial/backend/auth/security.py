from datetime import datetime, timedelta
from uuid import uuid4

from fastapi import Depends, HTTPException, Request, status
import jwt
from jwt import InvalidTokenError
from passlib.context import CryptContext
from sqlalchemy import func
from sqlalchemy.orm import Session

from backend.config import settings
from backend.database import get_db
from backend.models import CarteiraFerramentaConfig, User, UserSession


pwd_context = CryptContext(schemes=["pbkdf2_sha256"], deprecated="auto")

ROLE_PERMISSIONS = {
    "ADMIN": {"*"},
    "GERENCIAL": {"producao:read", "pareceres:read", "reports:read"},
    "SUPERVISOR": {"producao:read", "pareceres:read"},
    "USER": {"producao:write", "pareceres:write"},
    "NEGOCIADOR": {"producao:write", "pareceres:write"},
}


def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    return pwd_context.verify(password, password_hash)


def create_session_token() -> str:
    return uuid4().hex


def create_access_token(user: User, session_token: str, expires_at: datetime) -> str:
    payload = {
        "sub": str(user.id),
        "sid": session_token,
        "role": user.role,
        "exp": expires_at,
    }
    return jwt.encode(payload, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)


def get_request_token(request: Request) -> str | None:
    cookie_token = request.cookies.get(settings.auth_cookie_name)
    if cookie_token:
        return cookie_token

    authorization = request.headers.get("Authorization", "")
    if authorization.lower().startswith("bearer "):
        return authorization.split(" ", 1)[1].strip()
    return None


def get_current_user(request: Request, db: Session = Depends(get_db)) -> User:
    token = get_request_token(request)
    if not token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Nao autenticado.")

    try:
        payload = jwt.decode(token, settings.jwt_secret_key, algorithms=[settings.jwt_algorithm])
    except InvalidTokenError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Sessao invalida.") from exc

    user_id = payload.get("sub")
    session_token = payload.get("sid")
    if not user_id or not session_token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Sessao invalida.")

    session = (
        db.query(UserSession)
        .filter(UserSession.user_id == int(user_id), UserSession.token == session_token)
        .first()
    )
    if not session:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Sessao expirada.")
    now = datetime.now(session.expires_at.tzinfo) if session.expires_at.tzinfo else datetime.utcnow()
    if session.revoked_at or session.expires_at < now:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Sessao expirada.")

    user = db.query(User).filter(User.id == int(user_id), User.active.is_(True)).first()
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Usuario inativo.")
    return user


def require_admin(user: User = Depends(get_current_user)) -> User:
    if str(user.role or "").upper() != "ADMIN":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Permissao insuficiente.")
    return user


def enabled_tools(user: User) -> set[str]:
    raw_value = getattr(user, "enabled_tools", None)
    if raw_value is None:
        return {"producao", "pareceres"}
    raw = str(raw_value)
    tools = {item.strip().lower() for item in raw.split(",") if item.strip()}
    return tools


def wallet_tool_enabled(db, user: User, tool_key: str) -> bool:
    key = str(tool_key or "").strip().lower()
    if key == "producao":
        return True
    wallet = str(getattr(user, "carteira", "") or "").strip().upper()
    if not wallet:
        return True
    row = (
        db.query(CarteiraFerramentaConfig)
        .filter(
            func.upper(CarteiraFerramentaConfig.carteira) == wallet,
            func.lower(CarteiraFerramentaConfig.tool_key) == key,
        )
        .first()
    )
    return True if row is None else bool(row.enabled)


def effective_enabled_tools(db, user: User) -> set[str]:
    return {tool for tool in enabled_tools(user) if wallet_tool_enabled(db, user, tool)}


def require_tool(user: User, tool: str, db=None) -> None:
    if tool not in enabled_tools(user) or (db is not None and not wallet_tool_enabled(db, user, tool)):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Ferramenta nao habilitada para este usuario.")


def user_permissions(user: User) -> set[str]:
    role = str(user.role or "USER").upper()
    permissions = set(ROLE_PERMISSIONS.get(role, ROLE_PERMISSIONS["USER"]))
    for tool in enabled_tools(user):
        permissions.add(f"{tool}:read")
        if role in {"ADMIN", "USER", "NEGOCIADOR"}:
            permissions.add(f"{tool}:write")
    return permissions


def has_permission(user: User, permission: str) -> bool:
    permissions = user_permissions(user)
    return "*" in permissions or permission in permissions


def require_permission(user: User, permission: str) -> None:
    if not has_permission(user, permission):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Permissao insuficiente.")


def token_expiration() -> datetime:
    return datetime.utcnow() + timedelta(minutes=settings.access_token_expire_minutes)
