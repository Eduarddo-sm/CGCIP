from __future__ import annotations

import os
import sys
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import psycopg
from sqlalchemy.engine import make_url

from backend.config import settings
from backend.services.schema_migration_service import run_schema_migrations


EXPECTED_HEAD = "20260720_0011"


def _native_url(value: str) -> str:
    return value.replace("postgresql+psycopg://", "postgresql://", 1)


def main() -> None:
    source = make_url(settings.database_url)
    database_name = f"negocial_migration_test_{uuid.uuid4().hex[:8]}"
    admin_url = os.environ.get("POSTGRES_ADMIN_URL", "").strip()
    if not admin_url:
        admin_url = source.set(
            drivername="postgresql", username="postgres", database="postgres"
        ).render_as_string(hide_password=False)
    owner = source.username or "projeto_user"
    test_url = source.set(
        drivername="postgresql+psycopg", database=database_name
    ).render_as_string(hide_password=False)

    with psycopg.connect(_native_url(admin_url), autocommit=True) as connection:
        connection.execute(f'CREATE DATABASE "{database_name}" OWNER "{owner}"')
    try:
        run_schema_migrations(test_url, ROOT)
        with psycopg.connect(_native_url(test_url)) as connection:
            version = connection.execute("SELECT version_num FROM negocial.alembic_version").fetchone()[0]
            invalid_indexes = connection.execute(
                """
                SELECT COUNT(*)
                FROM pg_index i
                JOIN pg_class c ON c.oid = i.indexrelid
                JOIN pg_namespace n ON n.oid = c.relnamespace
                WHERE n.nspname = 'negocial' AND NOT i.indisvalid
                """
            ).fetchone()[0]
            table_count = connection.execute(
                """
                SELECT COUNT(*) FROM information_schema.tables
                WHERE table_schema = 'negocial' AND table_type = 'BASE TABLE'
                """
            ).fetchone()[0]
            if version != EXPECTED_HEAD:
                raise RuntimeError(f"Revision inesperada: {version}; esperado: {EXPECTED_HEAD}")
            if invalid_indexes:
                raise RuntimeError(f"Indices invalidos no banco isolado: {invalid_indexes}")
            if table_count < 20:
                raise RuntimeError(f"Schema incompleto: apenas {table_count} tabelas")
            print(f"OK: {version}; {table_count} tabelas; zero indices invalidos")
    finally:
        with psycopg.connect(_native_url(admin_url), autocommit=True) as connection:
            connection.execute(
                "SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname = %s",
                (database_name,),
            )
            connection.execute(f'DROP DATABASE IF EXISTS "{database_name}"')


if __name__ == "__main__":
    main()
