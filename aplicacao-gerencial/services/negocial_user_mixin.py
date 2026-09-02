from __future__ import annotations

import secrets
from datetime import date, datetime
from typing import Any


class NegocialUserMixin:
    @staticmethod
    def _goal_competence(value: Any = None) -> date:
        text = str(value or "").strip()
        if not text:
            today = date.today()
            return today.replace(day=1)
        try:
            year, month = (int(part) for part in text[:7].split("-"))
            return date(year, month, 1)
        except (TypeError, ValueError) as exc:
            raise ValueError("Competencia invalida. Use o formato AAAA-MM.") from exc

    def _upsert_monthly_goal(self, conn, user_id: int, competence: date, meta: Any, updated_by: str | None = None) -> None:
        now = self._now()
        if self.database_backend == "postgresql":
            conn.execute(
                """
                INSERT INTO user_monthly_goals (user_id, competencia, meta_pagamento, updated_by, created_at, updated_at)
                VALUES (%s, %s, %s, %s, %s, %s)
                ON CONFLICT (user_id, competencia) DO UPDATE SET
                    meta_pagamento = EXCLUDED.meta_pagamento,
                    updated_by = EXCLUDED.updated_by,
                    updated_at = EXCLUDED.updated_at
                """,
                (user_id, competence, meta, updated_by, now, now),
            )
            return
        conn.execute(
            """
            INSERT INTO user_monthly_goals (user_id, competencia, meta_pagamento, updated_by, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(user_id, competencia) DO UPDATE SET
                meta_pagamento = excluded.meta_pagamento,
                updated_by = excluded.updated_by,
                updated_at = excluded.updated_at
            """,
            (user_id, competence.isoformat(), float(meta), updated_by, now, now),
        )

    def list_user_monthly_goals(self, user_id: int) -> dict[str, Any]:
        if self.database_backend == "postgresql":
            with self._connect_postgres() as conn:
                user = conn.execute("SELECT meta_pagamento FROM users WHERE id = %s", (user_id,)).fetchone()
                if not user:
                    raise ValueError("Negociador nao encontrado.")
                rows = conn.execute(
                    "SELECT competencia, meta_pagamento, updated_by, updated_at FROM user_monthly_goals WHERE user_id = %s ORDER BY competencia DESC",
                    (user_id,),
                ).fetchall()
        else:
            with self.connect() as conn:
                self._ensure_expected_schema(conn)
                user = conn.execute("SELECT meta_pagamento FROM users WHERE id = ?", (user_id,)).fetchone()
                if not user:
                    raise ValueError("Negociador nao encontrado.")
                rows = conn.execute(
                    "SELECT competencia, meta_pagamento, updated_by, updated_at FROM user_monthly_goals WHERE user_id = ? ORDER BY competencia DESC",
                    (user_id,),
                ).fetchall()
        items = []
        for raw in rows:
            row = dict(raw)
            competence = row.get("competencia")
            items.append({
                "competencia": competence.strftime("%Y-%m") if hasattr(competence, "strftime") else str(competence or "")[:7],
                "meta_pagamento": float(row.get("meta_pagamento") or 0),
                "updated_by": row.get("updated_by"),
                "updated_at": str(row.get("updated_at") or ""),
            })
        return {"items": items, "fallback": float(dict(user).get("meta_pagamento") or 0)}

    def upsert_user(
        self,
        username: str,
        password: str | None,
        carteira: str,
        meta_pagamento: Any = None,
        enabled_tools: Any = None,
    ) -> dict[str, Any]:
        username = self._clean_required(username, "Usuario")
        carteira = self._clean_required(carteira, "Carteira").upper()
        meta = self._money(meta_pagamento if meta_pagamento not in (None, "") else 70000)
        tools = self._tools_text(enabled_tools)
        now = self._now()
        if self.database_backend == "postgresql":
            return self._upsert_user_postgres(username, password, carteira, meta, tools, now)
        with self.connect() as conn:
            self._ensure_expected_schema(conn)
            current = conn.execute("SELECT * FROM users WHERE username = ?", (username,)).fetchone()
            if current:
                params: list[Any] = [carteira, float(meta), tools, "USER", 1, now]
                password_sql = ""
                if password:
                    password_sql = "password_hash = ?, "
                    params.insert(0, self.hash_password(password))
                params.append(int(current["id"]))
                conn.execute(
                    f"""
                    UPDATE users
                    SET {password_sql}carteira = ?, meta_pagamento = ?, enabled_tools = ?, role = ?, active = ?, updated_at = ?
                    WHERE id = ?
                    """,
                    params,
                )
                user_id = int(current["id"])
            else:
                password = self._clean_required(password or "", "Senha")
                cur = conn.execute(
                    """
                    INSERT INTO users (
                        username, password_hash, role, carteira, meta_pagamento, enabled_tools, active, created_at, updated_at
                    )
                    VALUES (?, ?, 'USER', ?, ?, ?, 1, ?, ?)
                    """,
                    (username, self.hash_password(password), carteira, float(meta), tools, now, now),
                )
                user_id = int(cur.lastrowid)
            self._upsert_monthly_goal(conn, user_id, self._goal_competence(), meta, username)
            user = conn.execute("SELECT id, username, role, carteira, meta_pagamento, enabled_tools, active FROM users WHERE id = ?", (user_id,)).fetchone()
            return self._public_negocial_user(dict(user))

    def update_user_settings(self, user_id: int, payload: dict[str, Any], updated_by: str | None = None) -> dict[str, Any]:
        carteira = self._clean_required(payload.get("carteira", ""), "Carteira").upper()
        competence = self._goal_competence(payload.get("meta_competencia"))
        tools = self._tools_text(payload.get("enabled_tools"))
        password = str(payload.get("password") or "")
        now = self._now()
        if self.database_backend == "postgresql":
            with self._connect_postgres() as conn:
                row = conn.execute("SELECT id, meta_pagamento FROM users WHERE id = %s", (user_id,)).fetchone()
                if not row:
                    raise ValueError("Negociador nao encontrado.")
                meta = self._money(payload.get("meta_pagamento") if payload.get("meta_pagamento") not in (None, "") else row["meta_pagamento"])
                legacy_meta = meta if competence == self._goal_competence() else row["meta_pagamento"]
                if password:
                    conn.execute(
                        """
                        UPDATE users
                        SET password_hash = %s, carteira = %s, meta_pagamento = %s,
                            enabled_tools = %s, role = 'USER', updated_at = %s
                        WHERE id = %s
                        """,
                        (self.hash_password(password), carteira, legacy_meta, tools, now, user_id),
                    )
                else:
                    conn.execute(
                        """
                        UPDATE users
                        SET carteira = %s, meta_pagamento = %s,
                            enabled_tools = %s, role = 'USER', updated_at = %s
                        WHERE id = %s
                        """,
                        (carteira, legacy_meta, tools, now, user_id),
                    )
                self._upsert_monthly_goal(conn, user_id, competence, meta, updated_by)
                updated = conn.execute(
                    """
                    SELECT id, username, role, carteira, meta_pagamento, enabled_tools, active,
                           created_at, updated_at, 0 AS online_sessions
                    FROM users
                    WHERE id = %s
                    """,
                    (user_id,),
                ).fetchone()
                return self._public_negocial_user(dict(updated))
        with self.connect() as conn:
            self._ensure_expected_schema(conn)
            row = conn.execute("SELECT id, meta_pagamento FROM users WHERE id = ?", (user_id,)).fetchone()
            if not row:
                raise ValueError("Negociador nao encontrado.")
            meta = self._money(payload.get("meta_pagamento") if payload.get("meta_pagamento") not in (None, "") else row["meta_pagamento"])
            legacy_meta = meta if competence == self._goal_competence() else row["meta_pagamento"]
            if password:
                conn.execute(
                    """
                    UPDATE users
                    SET password_hash = ?, carteira = ?, meta_pagamento = ?,
                        enabled_tools = ?, role = 'USER', updated_at = ?
                    WHERE id = ?
                    """,
                    (self.hash_password(password), carteira, float(legacy_meta), tools, now, user_id),
                )
            else:
                conn.execute(
                    """
                    UPDATE users
                    SET carteira = ?, meta_pagamento = ?, enabled_tools = ?, role = 'USER', updated_at = ?
                    WHERE id = ?
                    """,
                    (carteira, float(legacy_meta), tools, now, user_id),
                )
            self._upsert_monthly_goal(conn, user_id, competence, meta, updated_by)
            updated = conn.execute(
                """
                SELECT id, username, role, carteira, meta_pagamento, enabled_tools, active,
                       created_at, updated_at, 0 AS online_sessions
                FROM users
                WHERE id = ?
                """,
                (user_id,),
            ).fetchone()
            return self._public_negocial_user(dict(updated))

    def list_users(self) -> list[dict[str, Any]]:
        if self.database_backend == "postgresql":
            return self._list_users_postgres()
        with self.connect() as conn:
            self._ensure_expected_schema(conn)
            rows = conn.execute(
                """
                SELECT
                    u.id,
                    u.username,
                    u.role,
                    u.carteira,
                    COALESCE(mg.meta_pagamento, u.meta_pagamento) AS meta_pagamento,
                    u.enabled_tools,
                    u.active,
                    u.created_at,
                    u.updated_at,
                    SUM(CASE WHEN s.expires_at > ? AND s.revoked_at IS NULL THEN 1 ELSE 0 END) AS online_sessions,
                    MAX(s.created_at) AS last_access_at
                FROM users u
                LEFT JOIN user_monthly_goals mg
                  ON mg.user_id = u.id AND mg.competencia = date('now', 'start of month')
                LEFT JOIN sessions s ON s.user_id = u.id
                WHERE COALESCE(u.password_hash, '') NOT LIKE '$deleted$%'
                GROUP BY u.id, u.username, u.role, u.carteira, u.meta_pagamento, mg.meta_pagamento, u.enabled_tools, u.active, u.created_at, u.updated_at
                ORDER BY u.username
                """,
                (datetime.utcnow().isoformat(sep=" ", timespec="seconds"),),
            ).fetchall()
        return [self._public_negocial_user(dict(row)) for row in rows]

    def set_user_active(self, user_id: int, active: bool) -> dict[str, Any]:
        now = self._now()
        if self.database_backend == "postgresql":
            return self._set_user_active_postgres(user_id, active, now)
        with self.connect() as conn:
            self._ensure_expected_schema(conn)
            row = conn.execute("SELECT id FROM users WHERE id = ?", (user_id,)).fetchone()
            if not row:
                raise ValueError("Negociador nao encontrado.")
            conn.execute("UPDATE users SET active = ?, updated_at = ? WHERE id = ?", (bool(active), now, user_id))
            if not active:
                conn.execute("UPDATE sessions SET revoked_at = ? WHERE user_id = ? AND revoked_at IS NULL", (now, user_id))
            updated = conn.execute(
                "SELECT id, username, role, carteira, meta_pagamento, enabled_tools, active, created_at, updated_at, 0 AS online_sessions FROM users WHERE id = ?",
                (user_id,),
            ).fetchone()
            return self._public_negocial_user(dict(updated))

    def delete_user_login(self, user_id: int) -> None:
        now = self._now()
        random_hash = self.hash_password(secrets.token_urlsafe(24))
        if self.database_backend == "postgresql":
            with self._connect_postgres() as conn:
                row = conn.execute("SELECT id FROM users WHERE id = %s", (user_id,)).fetchone()
                if not row:
                    raise ValueError("Negociador nao encontrado.")
                conn.execute(
                    "UPDATE users SET active = FALSE, password_hash = %s, updated_at = %s WHERE id = %s",
                    (f"$deleted${random_hash}", now, user_id),
                )
                conn.execute("UPDATE sessions SET revoked_at = %s WHERE user_id = %s AND revoked_at IS NULL", (now, user_id))
            return
        with self.connect() as conn:
            self._ensure_expected_schema(conn)
            row = conn.execute("SELECT id FROM users WHERE id = ?", (user_id,)).fetchone()
            if not row:
                raise ValueError("Negociador nao encontrado.")
            conn.execute(
                "UPDATE users SET active = 0, password_hash = ?, updated_at = ? WHERE id = ?",
                (f"$deleted${random_hash}", now, user_id),
            )
            conn.execute("UPDATE sessions SET revoked_at = ? WHERE user_id = ? AND revoked_at IS NULL", (now, user_id))

    def _upsert_user_postgres(self, username: str, password: str | None, carteira: str, meta: float, tools: str, now: str) -> dict[str, Any]:
        with self._connect_postgres() as conn:
            current = conn.execute("SELECT * FROM users WHERE username = %s", (username,)).fetchone()
            if current:
                if password:
                    conn.execute(
                        """
                        UPDATE users
                        SET password_hash = %s, carteira = %s, meta_pagamento = %s,
                            enabled_tools = %s, role = 'USER', active = TRUE, updated_at = %s
                        WHERE id = %s
                        """,
                        (self.hash_password(password), carteira, meta, tools, now, int(current["id"])),
                    )
                else:
                    conn.execute(
                        """
                        UPDATE users
                        SET carteira = %s, meta_pagamento = %s,
                            enabled_tools = %s, role = 'USER', active = TRUE, updated_at = %s
                        WHERE id = %s
                        """,
                        (carteira, meta, tools, now, int(current["id"])),
                    )
                user_id = int(current["id"])
            else:
                password = self._clean_required(password or "", "Senha")
                row = conn.execute(
                    """
                    INSERT INTO users (
                        username, password_hash, role, carteira, meta_pagamento, enabled_tools, active, created_at, updated_at
                    )
                    VALUES (%s, %s, 'USER', %s, %s, %s, TRUE, %s, %s)
                    RETURNING id
                    """,
                    (username, self.hash_password(password), carteira, meta, tools, now, now),
                ).fetchone()
                user_id = int(row["id"])
            user = conn.execute(
                "SELECT id, username, role, carteira, meta_pagamento, enabled_tools, active FROM users WHERE id = %s",
                (user_id,),
            ).fetchone()
            self._upsert_monthly_goal(conn, user_id, self._goal_competence(), meta, username)
            return self._public_negocial_user(dict(user))

    def _list_users_postgres(self) -> list[dict[str, Any]]:
        with self._connect_postgres() as conn:
            rows = conn.execute(
                """
                SELECT
                    u.id,
                    u.username,
                    u.role,
                    u.carteira,
                    COALESCE(mg.meta_pagamento, u.meta_pagamento) AS meta_pagamento,
                    u.enabled_tools,
                    u.active,
                    u.created_at,
                    u.updated_at,
                    COUNT(s.id) FILTER (WHERE s.expires_at > NOW() AND s.revoked_at IS NULL) AS online_sessions,
                    MAX(s.created_at) AS last_access_at
                FROM users u
                LEFT JOIN user_monthly_goals mg
                  ON mg.user_id = u.id AND mg.competencia = DATE_TRUNC('month', CURRENT_DATE)::date
                LEFT JOIN sessions s ON s.user_id = u.id
                WHERE COALESCE(u.password_hash, '') NOT LIKE '$deleted$%'
                GROUP BY u.id, u.username, u.role, u.carteira, u.meta_pagamento, mg.meta_pagamento, u.enabled_tools, u.active, u.created_at, u.updated_at
                ORDER BY u.username
                """
            ).fetchall()
        return [self._public_negocial_user(dict(row)) for row in rows]

    def _set_user_active_postgres(self, user_id: int, active: bool, now: str) -> dict[str, Any]:
        with self._connect_postgres() as conn:
            row = conn.execute("SELECT id FROM users WHERE id = %s", (user_id,)).fetchone()
            if not row:
                raise ValueError("Negociador nao encontrado.")
            conn.execute("UPDATE users SET active = %s, updated_at = %s WHERE id = %s", (bool(active), now, user_id))
            if not active:
                conn.execute("UPDATE sessions SET revoked_at = %s WHERE user_id = %s AND revoked_at IS NULL", (now, user_id))
            updated = conn.execute(
                """
                SELECT id, username, role, carteira, meta_pagamento, enabled_tools, active, created_at, updated_at, 0 AS online_sessions
                FROM users
                WHERE id = %s
                """,
                (user_id,),
            ).fetchone()
            return self._public_negocial_user(dict(updated))
