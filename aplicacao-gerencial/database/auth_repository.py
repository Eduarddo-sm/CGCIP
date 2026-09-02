from __future__ import annotations

import hashlib
import hmac
import secrets
from datetime import datetime, timedelta
from typing import Any, Callable


class AuthRepository:
    def __init__(self, connect: Callable[[], Any], lock: Any) -> None:
        self.connect = connect
        self.lock = lock

    def authenticate(self, username: str, password: str) -> dict[str, Any] | None:
        with self.lock, self.connect() as conn:
            row = conn.execute("SELECT * FROM users WHERE lower(username) = lower(?) AND active = 1", (username,)).fetchone()
            if not row:
                return None
            user = dict(row)

        # PBKDF2 is intentionally expensive. Keeping the repository lock while
        # hashing serializes simultaneous logins and blocks unrelated reads.
        candidate = self.hash_password(password, user["salt"])
        if not hmac.compare_digest(candidate, user["password_hash"]):
            return None
        return self.public_user(user)

    def create_session(self, username: str, ttl_hours: int = 24 * 30) -> str:
        user = self.user_by_username(username)
        if not user:
            raise ValueError("Usuario nao encontrado")
        token = secrets.token_urlsafe(32)
        now = datetime.now()
        expires_at = now + timedelta(hours=ttl_hours)
        with self.lock, self.connect() as conn:
            conn.execute(
                "INSERT INTO sessions (token, user_id, created_at, expires_at) VALUES (?, ?, ?, ?)",
                (token, user["id"], now.isoformat(timespec="seconds"), expires_at.isoformat(timespec="seconds")),
            )
        return token

    def user_by_username(self, username: str) -> dict[str, Any] | None:
        with self.lock, self.connect() as conn:
            row = conn.execute("SELECT * FROM users WHERE lower(username) = lower(?) AND active = 1", (username,)).fetchone()
            return self.public_user(dict(row)) if row else None

    def user_by_session(self, token: str | None) -> dict[str, Any] | None:
        if not token:
            return None
        with self.lock, self.connect() as conn:
            row = conn.execute(
                """
                SELECT u.*
                FROM sessions s
                JOIN users u ON u.id = s.user_id
                WHERE s.token = ? AND u.active = 1 AND s.expires_at > ?
                """,
                (token, datetime.now().isoformat(timespec="seconds")),
            ).fetchone()
            return self.public_user(dict(row)) if row else None

    def delete_session(self, token: str | None) -> None:
        if not token:
            return
        with self.lock, self.connect() as conn:
            conn.execute("DELETE FROM sessions WHERE token = ?", (token,))

    @staticmethod
    def hash_password(password: str, salt: str) -> str:
        return hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt.encode("utf-8"), 120_000).hex()

    @staticmethod
    def public_user(user: dict[str, Any]) -> dict[str, Any]:
        return {"id": user["id"], "username": user["username"], "role": user["role"], "active": user.get("active", True)}
