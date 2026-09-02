from datetime import datetime

from fastapi import HTTPException, status
from sqlalchemy.orm import Session
from sqlalchemy import func

from backend.auth.security import (
    create_access_token,
    create_session_token,
    token_expiration,
    verify_password,
)
from backend.models import User, UserSession


def authenticate_user(db: Session, username: str, password: str) -> tuple[User, UserSession, str]:
    user = db.query(User).filter(func.lower(User.username) == username.strip().lower()).first()
    if not user or not user.active or not verify_password(password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Usuario ou senha invalidos.",
        )

    session_token = create_session_token()
    expires_at = token_expiration()
    session = UserSession(user_id=user.id, token=session_token, expires_at=expires_at)
    db.add(session)
    db.commit()
    db.refresh(session)

    access_token = create_access_token(user, session_token, expires_at)
    return user, session, access_token


def revoke_session(db: Session, session_token: str | None):
    if not session_token:
        return
    session = db.query(UserSession).filter(UserSession.token == session_token).first()
    if session and not session.revoked_at:
        session.revoked_at = datetime.utcnow()
        db.commit()
