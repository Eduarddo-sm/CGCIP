from __future__ import annotations

import os
from pathlib import Path


MIGRATION_LOCK_ID = 876520260720


def _sqlalchemy_url(database_url: str) -> str:
    if database_url.startswith("postgresql+psycopg://"):
        return database_url
    if database_url.startswith("postgresql://"):
        return database_url.replace("postgresql://", "postgresql+psycopg://", 1)
    if database_url.startswith("postgres://"):
        return database_url.replace("postgres://", "postgresql+psycopg://", 1)
    return database_url


def run_schema_migrations(database_url: str, root: Path | None = None) -> None:
    """Upgrade PostgreSQL before repositories start serving requests."""
    if not str(database_url).startswith(("postgresql://", "postgresql+psycopg://")):
        return
    if os.environ.get("GERENCIAL_SKIP_MIGRATIONS", "").strip().lower() in {"1", "true", "yes"}:
        return
    try:
        import psycopg
        from alembic import command
        from alembic.config import Config
    except ImportError as exc:
        raise RuntimeError("PostgreSQL requer Alembic e psycopg para validar o schema.") from exc

    project_root = Path(root or Path(__file__).resolve().parents[1])
    normalized_url = database_url.replace("postgresql+psycopg://", "postgresql://", 1)
    with psycopg.connect(normalized_url, autocommit=True) as connection:
        connection.execute("SELECT pg_advisory_lock(%s)", (MIGRATION_LOCK_ID,))
        try:
            config = Config(str(project_root / "alembic.ini"))
            config.set_main_option("script_location", str(project_root / "database" / "migrations"))
            migration_url = _sqlalchemy_url(database_url)
            config.set_main_option("sqlalchemy.url", migration_url.replace("%", "%%"))
            previous_url = os.environ.get("DATABASE_URL")
            os.environ["DATABASE_URL"] = migration_url
            try:
                command.upgrade(config, "head")
            finally:
                if previous_url is None:
                    os.environ.pop("DATABASE_URL", None)
                else:
                    os.environ["DATABASE_URL"] = previous_url
        finally:
            connection.execute("SELECT pg_advisory_unlock(%s)", (MIGRATION_LOCK_ID,))
