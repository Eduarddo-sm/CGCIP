from __future__ import annotations

from datetime import datetime
from typing import Any


class NegocialParecerMixin:
    def read_parecer_records(self) -> list[dict[str, Any]]:
        if self.database_backend == "postgresql":
            return self._read_parecer_records_postgres()
        with self.connect() as conn:
            self._ensure_expected_schema(conn)
            self._ensure_parecer_schema(conn)
            rows = conn.execute(
                """
                SELECT p.*, u.username AS operador
                FROM pareceres p
                JOIN users u ON u.id = p.user_id
                ORDER BY p.created_at DESC, p.id DESC
                """
            ).fetchall()
        return [self._map_parecer_row(row, index) for index, row in enumerate(rows, start=1)]

    def read_parecer_pendentes(self) -> list[dict[str, Any]]:
        return [
            row for row in self.read_parecer_records()
            if row.get("STATUS") == "PENDENTE" and row.get("APROVACAO") == "APROVADO"
        ]

    def read_parecer_approval_pending(self) -> list[dict[str, Any]]:
        return [
            row for row in self.read_parecer_records()
            if row.get("__source") == "sistema"
            and row.get("STATUS") == "PENDENTE"
            and row.get("APROVACAO") == "PENDENTE"
        ]

    def read_parecer_approval_history(self) -> list[dict[str, Any]]:
        return [
            row for row in self.read_parecer_records()
            if row.get("__source") == "sistema"
            and row.get("APROVACAO") in {"APROVADO", "REPROVADO"}
        ]

    def read_parecer_approval_rejected(self) -> list[dict[str, Any]]:
        return [row for row in self.read_parecer_approval_history() if row.get("APROVACAO") == "REPROVADO"]

    def parecer_marker(self) -> str:
        if self.database_backend == "postgresql":
            with self._connect_postgres() as conn:
                row = conn.execute(
                    """
                    SELECT
                        COUNT(*) AS total_rows,
                        COALESCE(MAX(id), 0) AS max_row_id,
                        COALESCE(MAX(updated_at)::text, '') AS last_update
                    FROM pareceres
                    """
                ).fetchone()
            return "|".join(
                [
                    str(row["total_rows"] or 0),
                    str(row["max_row_id"] or 0),
                    str(row["last_update"] or ""),
                ]
            )
        with self.connect() as conn:
            self._ensure_parecer_schema(conn)
            row = conn.execute(
                """
                SELECT
                    COUNT(*) AS total_rows,
                    COALESCE(MAX(id), 0) AS max_row_id,
                    COALESCE(MAX(updated_at), '') AS last_update
                FROM pareceres
                """
            ).fetchone()
        return "|".join(
            [
                str(row["total_rows"] or 0),
                str(row["max_row_id"] or 0),
                str(row["last_update"] or ""),
            ]
        )

    def marcar_parecer_solicitado(self, parecer_id: int, username: str = "gerencial") -> dict[str, Any]:
        now = self._now()
        if self.database_backend == "postgresql":
            return self._marcar_parecer_solicitado_postgres(parecer_id, username, now)
        with self.connect() as conn:
            self._ensure_expected_schema(conn)
            self._ensure_parecer_schema(conn)
            current = conn.execute("SELECT id, status, approval_status FROM pareceres WHERE id = ?", (parecer_id,)).fetchone()
            if not current:
                raise ValueError(f"Parecer negocial nao encontrado: {parecer_id}")
            if str(current["approval_status"] or "PENDENTE").upper() != "APROVADO":
                raise ValueError("Parecer ainda nao aprovado.")
            duplicated = str(current["status"] or "").upper() == "SOLICITADO"
            if not duplicated:
                conn.execute(
                    """
                    UPDATE pareceres
                    SET status = 'SOLICITADO', data_conclusao = NULL, requested_at = ?, updated_at = ?
                    WHERE id = ?
                    """,
                    (now, now, parecer_id),
                )
        return {
            "ok": True,
            "pk": self.parecer_pk(parecer_id),
            "id": parecer_id,
            "duplicated": duplicated,
            "source": "sistema",
            "updated_by": username,
        }

    def _read_parecer_records_postgres(self) -> list[dict[str, Any]]:
        with self._connect_postgres() as conn:
            rows = conn.execute(
                """
                SELECT p.*, u.username AS operador
                FROM pareceres p
                JOIN users u ON u.id = p.user_id
                WHERE COALESCE(u.password_hash, '') NOT LIKE '$deleted$%'
                ORDER BY p.created_at DESC, p.id DESC
                """
            ).fetchall()
        return [self._map_parecer_row(row, index) for index, row in enumerate(rows, start=1)]

    def aprovar_parecer(self, parecer_id: int, reason: str, descricao: str, username: str = "gerencial") -> dict[str, Any]:
        reason = str(reason or "").strip()
        descricao = str(descricao or "").strip()
        if not reason:
            raise ValueError("Informe a justificativa da aprovação.")
        if not descricao:
            raise ValueError("Informe a descrição do parecer.")
        now = self._now()
        if self.database_backend == "postgresql":
            with self._connect_postgres() as conn:
                current = conn.execute("SELECT id FROM pareceres WHERE id = %s", (parecer_id,)).fetchone()
                if not current:
                    raise ValueError(f"Parecer negocial nao encontrado: {parecer_id}")
                conn.execute(
                    """
                    UPDATE pareceres
                    SET descricao = %s,
                        approval_status = 'APROVADO',
                        approval_reason = %s,
                        approval_decided_at = %s,
                        updated_at = %s
                    WHERE id = %s
                    """,
                    (descricao[:1000], reason[:600], now, now, parecer_id),
                )
            return {"ok": True, "pk": self.parecer_pk(parecer_id), "id": parecer_id, "updated_by": username}
        with self.connect() as conn:
            self._ensure_parecer_schema(conn)
            current = conn.execute("SELECT id FROM pareceres WHERE id = ?", (parecer_id,)).fetchone()
            if not current:
                raise ValueError(f"Parecer negocial nao encontrado: {parecer_id}")
            conn.execute(
                """
                UPDATE pareceres
                SET descricao = ?,
                    approval_status = 'APROVADO',
                    approval_reason = ?,
                    approval_decided_at = ?,
                    updated_at = ?
                WHERE id = ?
                """,
                (descricao[:1000], reason[:600], now, now, parecer_id),
            )
        return {"ok": True, "pk": self.parecer_pk(parecer_id), "id": parecer_id, "updated_by": username}

    def reprovar_parecer(self, parecer_id: int, reason: str, descricao: str, username: str = "gerencial") -> dict[str, Any]:
        reason = str(reason or "").strip()
        descricao = str(descricao or "").strip()
        if not reason:
            raise ValueError("Informe a justificativa da reprovação.")
        if not descricao:
            raise ValueError("Informe a descrição do parecer.")
        now = self._now()
        if self.database_backend == "postgresql":
            with self._connect_postgres() as conn:
                current = conn.execute("SELECT id FROM pareceres WHERE id = %s", (parecer_id,)).fetchone()
                if not current:
                    raise ValueError(f"Parecer negocial nao encontrado: {parecer_id}")
                conn.execute(
                    """
                    UPDATE pareceres
                    SET descricao = %s,
                        status = 'CANCELADO',
                        approval_status = 'REPROVADO',
                        approval_reason = %s,
                        approval_decided_at = %s,
                        data_conclusao = NULL,
                        updated_at = %s
                    WHERE id = %s
                    """,
                    (descricao[:1000], reason[:600], now, now, parecer_id),
                )
            return {"ok": True, "pk": self.parecer_pk(parecer_id), "id": parecer_id, "updated_by": username}
        with self.connect() as conn:
            self._ensure_parecer_schema(conn)
            current = conn.execute("SELECT id FROM pareceres WHERE id = ?", (parecer_id,)).fetchone()
            if not current:
                raise ValueError(f"Parecer negocial nao encontrado: {parecer_id}")
            conn.execute(
                """
                UPDATE pareceres
                SET descricao = ?,
                    status = 'CANCELADO',
                    approval_status = 'REPROVADO',
                    approval_reason = ?,
                    approval_decided_at = ?,
                    data_conclusao = NULL,
                    updated_at = ?
                WHERE id = ?
                """,
                (descricao[:1000], reason[:600], now, now, parecer_id),
            )
        return {"ok": True, "pk": self.parecer_pk(parecer_id), "id": parecer_id, "updated_by": username}

    def _marcar_parecer_solicitado_postgres(self, parecer_id: int, username: str, now: str) -> dict[str, Any]:
        with self._connect_postgres() as conn:
            current = conn.execute("SELECT id, status, approval_status FROM pareceres WHERE id = %s", (parecer_id,)).fetchone()
            if not current:
                raise ValueError(f"Parecer negocial nao encontrado: {parecer_id}")
            if str(current["approval_status"] or "PENDENTE").upper() != "APROVADO":
                raise ValueError("Parecer ainda nao aprovado.")
            duplicated = str(current["status"] or "").upper() == "SOLICITADO"
            if not duplicated:
                conn.execute(
                    """
                    UPDATE pareceres
                    SET status = 'SOLICITADO', data_conclusao = NULL, requested_at = %s, updated_at = %s
                    WHERE id = %s
                    """,
                    (now, now, parecer_id),
                )
        return {
            "ok": True,
            "pk": self.parecer_pk(parecer_id),
            "id": parecer_id,
            "duplicated": duplicated,
            "source": "sistema",
            "updated_by": username,
        }

    def parecer_pk(self, parecer_id: int) -> str:
        return f"NEGOCIAL:{int(parecer_id)}"
