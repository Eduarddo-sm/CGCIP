from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
import jwt
from jwt import InvalidTokenError
from sqlalchemy.orm import Session

from backend.auth.security import effective_enabled_tools, get_current_user
from backend.config import settings
from backend.database import get_db
from backend.models import User
from backend.schemas.auth import AuthResponse, LoginRequest, UserMetaUpdate, UserResponse
from backend.services.auth_service import authenticate_user, revoke_session
from backend.services.login_rate_limit import login_rate_limiter
from backend.services.user_goal_service import effective_goal, month_start, set_goal


router = APIRouter()


def serialize_user(user: User, db: Session) -> UserResponse:
    return UserResponse(
        id=user.id,
        username=user.username,
        role=user.role,
        carteira=user.carteira,
        meta_pagamento=float(effective_goal(db, user)),
        enabled_tools=sorted(effective_enabled_tools(db, user)),
        active=user.active,
    )


@router.post("/login", response_model=AuthResponse)
def login(payload: LoginRequest, request: Request, response: Response, db: Session = Depends(get_db)):
    client = request.client.host if request.client else "unknown"
    rate_key = f"{client}:{payload.username.strip().lower()}"
    retry_after = login_rate_limiter.retry_after(rate_key)
    if retry_after:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=f"Muitas tentativas. Tente novamente em {retry_after} segundos.",
            headers={"Retry-After": str(retry_after)},
        )
    try:
        user, session, token = authenticate_user(db, payload.username, payload.password)
    except HTTPException as exc:
        if exc.status_code == status.HTTP_401_UNAUTHORIZED:
            login_rate_limiter.failure(rate_key)
        raise
    login_rate_limiter.success(rate_key)
    now = datetime.now(session.expires_at.tzinfo) if session.expires_at.tzinfo else datetime.utcnow()
    max_age = int((session.expires_at - now).total_seconds())
    response.set_cookie(
        key=settings.auth_cookie_name,
        value=token,
        max_age=max_age,
        httponly=True,
        secure=settings.secure_cookies,
        samesite="lax",
    )
    return AuthResponse(user=serialize_user(user, db))


@router.post("/logout")
def logout(request: Request, response: Response, db: Session = Depends(get_db)):
    token = request.cookies.get(settings.auth_cookie_name)
    session_token = None
    if token:
        try:
            session_token = jwt.decode(
                token,
                settings.jwt_secret_key,
                algorithms=[settings.jwt_algorithm],
                options={"verify_exp": False},
            ).get("sid")
        except InvalidTokenError:
            session_token = None
    revoke_session(db, session_token)
    response.delete_cookie(
        settings.auth_cookie_name,
        httponly=True,
        secure=settings.secure_cookies,
        samesite="lax",
    )
    return {"ok": True}


@router.get("/me", response_model=AuthResponse)
def me(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    return AuthResponse(user=serialize_user(user, db))


@router.patch("/me/meta", response_model=AuthResponse)
def atualizar_meta(
    payload: UserMetaUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    set_goal(db, user, month_start(), payload.meta_pagamento, updated_by=user.username)
    db.refresh(user)
    return AuthResponse(user=serialize_user(user, db))
