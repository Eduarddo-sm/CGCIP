from __future__ import annotations

from typing import Any

from database.repository import Repository


class SnapshotRetentionService:
    """Retem snapshots historicos referenciados e o baseline atual de cada planilha."""

    _CTES = """
        WITH ranked AS (
            SELECT id, ROW_NUMBER() OVER (
                PARTITION BY negociador_id, sheet ORDER BY id DESC
            ) AS position
            FROM snapshots
        ),
        protected AS (
            SELECT id FROM ranked WHERE position = 1
            UNION
            SELECT snapshot_before_id FROM events WHERE snapshot_before_id IS NOT NULL
            UNION
            SELECT snapshot_after_id FROM events WHERE snapshot_after_id IS NOT NULL
        )
    """

    def __init__(self, repository: Repository) -> None:
        self.repository = repository

    def inspect(self) -> dict[str, Any]:
        with self.repository.connect() as conn:
            row = conn.execute(
                self._CTES
                + """
                SELECT
                    (SELECT COUNT(*) FROM snapshots) AS total,
                    (SELECT COUNT(*) FROM protected) AS protected,
                    (SELECT COUNT(*) FROM snapshots WHERE id NOT IN (SELECT id FROM protected)) AS removable
                """
            ).fetchone()
            result = dict(row)
            if self.repository.backend == "postgresql":
                size = conn.execute(
                    "SELECT pg_total_relation_size('gerencial.snapshots') AS relation_bytes"
                ).fetchone()
                result["relation_bytes"] = int(dict(size).get("relation_bytes") or 0)
            else:
                result["relation_bytes"] = None
            return {key: int(value) if value is not None else None for key, value in result.items()}

    def cleanup(self) -> dict[str, Any]:
        before = self.inspect()
        if not before["removable"]:
            return {"ok": True, "deleted": 0, "before": before, "after": before}
        with self.repository.connect() as conn:
            conn.execute(
                self._CTES
                + """
                DELETE FROM snapshots
                WHERE id NOT IN (SELECT id FROM protected)
                """
            )
            deleted = int(before["removable"] or 0)
        self.repository._snapshot_content_cache.clear()
        return {"ok": True, "deleted": deleted, "before": before, "after": self.inspect()}
