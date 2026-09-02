from __future__ import annotations

from typing import Any


class DatabaseConnection:
    """Small compatibility adapter for SQLite and pooled PostgreSQL connections."""

    def __init__(self, conn: Any, backend: str, owner_context: Any = None) -> None:
        self.conn = conn
        self.backend = backend
        self.owner_context = owner_context

    def __enter__(self) -> "DatabaseConnection":
        if self.owner_context is not None:
            self.conn = self.owner_context.__enter__()
            return self
        self.conn.__enter__()
        return self

    def __exit__(self, exc_type: Any, exc: Any, tb: Any) -> Any:
        if self.owner_context is not None:
            return self.owner_context.__exit__(exc_type, exc, tb)
        result = self.conn.__exit__(exc_type, exc, tb)
        self.conn.close()
        return result

    def execute(self, sql: str, params: Any = None) -> Any:
        return self.conn.execute(self._sql(sql), params or ())

    def executescript(self, script: str) -> None:
        if self.backend == "sqlite":
            self.conn.executescript(script)
            return
        for statement in script.split(";"):
            if statement.strip():
                self.execute(statement)

    def _sql(self, sql: str) -> str:
        if self.backend == "sqlite":
            return sql
        converted = sql.replace("INSERT OR IGNORE INTO", "INSERT INTO")
        converted = converted.replace("?", "%s")
        converted = converted.replace("active = 1", "active = TRUE")
        converted = converted.replace("active = 0", "active = FALSE")
        if "INSERT INTO overview_reads" in converted or "INSERT INTO notification_reads" in converted:
            converted += " ON CONFLICT DO NOTHING"
        return converted


class NoOpLock:
    """PostgreSQL connections are isolated by the pool and need no global lock."""

    def __enter__(self) -> "NoOpLock":
        return self

    def __exit__(self, exc_type: Any, exc: Any, tb: Any) -> None:
        return None
