from __future__ import annotations

import argparse
import os
import secrets
import sys
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

import psycopg
from psycopg import sql

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from services.schema_migration import run_schema_migrations


def migration_head() -> str:
    revisions = sorted(
        path.name.split("_", 2)[0] + "_" + path.name.split("_", 2)[1]
        for path in (ROOT / "database" / "migrations" / "versions").glob("*.py")
        if path.name[:1].isdigit() and len(path.name.split("_", 2)) >= 2
    )
    if not revisions:
        raise RuntimeError("Nenhuma migration gerencial encontrada.")
    return revisions[-1]


def load_env() -> None:
    env_file = ROOT / ".env"
    if not env_file.exists():
        return
    for line in env_file.read_text(encoding="utf-8").splitlines():
        if line.strip() and not line.lstrip().startswith("#") and "=" in line:
            key, value = line.split("=", 1)
            os.environ.setdefault(key.strip(), value.strip())


def database_url_with_name(database_url: str, database_name: str) -> str:
    parsed = urlsplit(database_url)
    return urlunsplit((parsed.scheme, parsed.netloc, f"/{database_name}", parsed.query, parsed.fragment))


def main() -> int:
    parser = argparse.ArgumentParser(description="Valida as migrations gerenciais em um banco PostgreSQL vazio.")
    parser.add_argument("--admin-url", default=os.environ.get("POSTGRES_ADMIN_URL", ""))
    args = parser.parse_args()
    load_env()
    application_url = os.environ.get("DATABASE_URL", "")
    admin_url = args.admin_url or os.environ.get("POSTGRES_ADMIN_URL", "")
    if not admin_url:
        parsed = urlsplit(application_url.replace("postgresql+psycopg://", "postgresql://", 1))
        if not parsed.password:
            raise SystemExit("Defina POSTGRES_ADMIN_URL com uma credencial autorizada a criar banco de teste.")
        host = parsed.hostname or "127.0.0.1"
        port = f":{parsed.port}" if parsed.port else ""
        admin_url = f"postgresql://postgres:{parsed.password}@{host}{port}/postgres"
    database_name = f"gerencial_migration_test_{secrets.token_hex(5)}"
    admin_database_url = database_url_with_name(admin_url, "postgres")
    test_url = database_url_with_name(application_url, database_name)
    with psycopg.connect(admin_database_url, autocommit=True) as admin:
        admin.execute(
            sql.SQL("CREATE DATABASE {} OWNER {} TEMPLATE template0").format(
                sql.Identifier(database_name),
                sql.Identifier("projeto_user"),
            )
        )
    try:
        run_schema_migrations(test_url, ROOT)
        with psycopg.connect(test_url.replace("postgresql+psycopg://", "postgresql://", 1)) as conn:
            tables = conn.execute("SELECT count(*) FROM information_schema.tables WHERE table_schema = 'gerencial' AND table_type = 'BASE TABLE'").fetchone()[0]
            constraints = conn.execute("SELECT count(*) FROM pg_constraint c JOIN pg_namespace n ON n.oid = c.connamespace WHERE n.nspname = 'gerencial'").fetchone()[0]
            indexes = conn.execute("SELECT count(*) FROM pg_indexes WHERE schemaname = 'gerencial'").fetchone()[0]
            version = conn.execute("SELECT version_num FROM gerencial.alembic_version").fetchone()[0]
        expected_version = migration_head()
        ok = tables >= 20 and constraints >= 20 and indexes >= 30 and version == expected_version
        print({"ok": ok, "tables": tables, "constraints": constraints, "indexes": indexes, "version": version})
        return 0 if ok else 1
    finally:
        with psycopg.connect(admin_database_url, autocommit=True) as admin:
            admin.execute("SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname = %s", (database_name,))
            admin.execute(sql.SQL("DROP DATABASE IF EXISTS {}").format(sql.Identifier(database_name)))


if __name__ == "__main__":
    raise SystemExit(main())
