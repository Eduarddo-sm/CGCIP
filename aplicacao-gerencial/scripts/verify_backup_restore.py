from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import tempfile
import sys
import time
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.config import settings
from services.database_backup import DatabaseBackupService


def run(command: list[str], env: dict[str, str] | None = None, timeout: int = 600) -> None:
    result = subprocess.run(command, env=env, capture_output=True, text=True, timeout=timeout)
    if result.returncode:
        raise RuntimeError((result.stderr or result.stdout or "Comando PostgreSQL falhou.").strip())


def newest_backup(service: DatabaseBackupService) -> Path:
    items = service.list_backups().get("items", [])
    if not items:
        raise RuntimeError("Nenhum backup PostgreSQL encontrado.")
    return Path(items[0]["path"])


def connect(parsed: dict[str, str], database: str):
    import psycopg

    return psycopg.connect(
        host=parsed["host"],
        port=int(parsed["port"]),
        user=parsed["username"],
        password=parsed["password"],
        dbname=database,
    )


def capture_manifest(conn, schema_map: dict[str, str] | None = None) -> dict[str, Any]:
    from psycopg import sql

    schema_map = schema_map or {"gerencial": "gerencial", "negocial": "negocial"}
    actual_schemas = list(schema_map)
    table_rows = conn.execute(
        """
        SELECT table_schema, table_name
        FROM information_schema.tables
        WHERE table_schema = ANY(%s)
          AND table_type = 'BASE TABLE'
        ORDER BY table_schema, table_name
        """,
        (actual_schemas,),
    ).fetchall()
    row_counts: dict[str, int] = {}
    for schema_name, table_name in table_rows:
        query = sql.SQL("SELECT count(*) FROM {}.{}").format(
            sql.Identifier(schema_name), sql.Identifier(table_name)
        )
        logical_schema = schema_map[schema_name]
        row_counts[f"{logical_schema}.{table_name}"] = int(conn.execute(query).fetchone()[0])

    views = [
        f"{schema_map[schema]}.{name}"
        for schema, name in conn.execute(
            """
            SELECT table_schema, table_name
            FROM information_schema.views
            WHERE table_schema = ANY(%s)
            ORDER BY table_schema, table_name
            """,
            (actual_schemas,),
        ).fetchall()
    ]
    constraints = int(
        conn.execute(
            """
            SELECT count(*)
            FROM information_schema.table_constraints
            WHERE table_schema = ANY(%s)
            """,
            (actual_schemas,),
        ).fetchone()[0]
    )
    indexes = int(
        conn.execute(
            """
            SELECT count(*)
            FROM pg_indexes
            WHERE schemaname = ANY(%s)
            """,
            (actual_schemas,),
        ).fetchone()[0]
    )
    versions: dict[str, str] = {}
    negocial_schema = next((actual for actual, logical in schema_map.items() if logical == "negocial"), "")
    if negocial_schema:
        version_query = sql.SQL("SELECT version_num FROM {}.alembic_version").format(sql.Identifier(negocial_schema))
        row = conn.execute(version_query).fetchone()
        if row:
            versions["alembic"] = str(row[0])
    return {
        "row_counts": row_counts,
        "views": views,
        "constraints": constraints,
        "indexes": indexes,
        "versions": versions,
    }

def create_consistent_backup(service: DatabaseBackupService, parsed: dict[str, str]) -> tuple[Path, dict[str, Any]]:
    with connect(parsed, parsed["database"]) as conn:
        conn.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY")
        snapshot = str(conn.execute("SELECT pg_export_snapshot()").fetchone()[0])
        manifest = capture_manifest(conn)
        result = service.create_backup("restore_validation", snapshot=snapshot)
        conn.rollback()
    return Path(result["backup"]["path"]), manifest


def create_validation_database(parsed: dict[str, str], database_name: str) -> None:
    from psycopg import sql

    with connect(parsed, "postgres") as conn:
        conn.autocommit = True
        conn.execute(sql.SQL("CREATE DATABASE {} TEMPLATE template0 ENCODING 'UTF8'").format(sql.Identifier(database_name)))


def drop_validation_database(parsed: dict[str, str], database_name: str) -> None:
    from psycopg import sql

    with connect(parsed, "postgres") as conn:
        conn.autocommit = True
        conn.execute(
            "SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname = %s AND pid <> pg_backend_pid()",
            (database_name,),
        )
        conn.execute(sql.SQL("DROP DATABASE IF EXISTS {}").format(sql.Identifier(database_name)))


def restore(service: DatabaseBackupService, parsed: dict[str, str], backup: Path, database_name: str) -> None:
    pg_restore = service._require_binary("pg_restore")
    env = os.environ.copy()
    if parsed.get("password"):
        env["PGPASSWORD"] = parsed["password"]
    run(
        [
            pg_restore,
            "--no-owner",
            "--no-privileges",
            "--exit-on-error",
            "--host", parsed["host"],
            "--port", parsed["port"],
            "--username", parsed["username"],
            "--dbname", database_name,
            str(backup),
        ]
    )



def _transform_restore_sql(source: Path, target: Path, schema_map: dict[str, str]) -> None:
    in_copy = False
    patterns = [(re.compile(rf"\b{re.escape(original)}\b"), replacement) for original, replacement in schema_map.items()]
    with source.open("r", encoding="utf-8") as reader, target.open("w", encoding="utf-8", newline="\n") as writer:
        for line in reader:
            if not in_copy:
                for pattern, replacement in patterns:
                    line = pattern.sub(replacement, line)
                if line.startswith("COPY ") and line.rstrip().endswith("FROM stdin;"):
                    in_copy = True
            elif line.rstrip("\r\n") == r"\.":
                in_copy = False
            writer.write(line)


def restore_into_isolated_schemas(
    service: DatabaseBackupService,
    parsed: dict[str, str],
    backup: Path,
    token: str,
) -> dict[str, str]:
    pg_restore = service._require_binary("pg_restore")
    psql = service._require_binary("psql")
    actual_map = {f"restore_g_{token}": "gerencial", f"restore_n_{token}": "negocial"}
    replacement_map = {logical: actual for actual, logical in actual_map.items()}
    from psycopg import sql
    with connect(parsed, parsed["database"]) as conn:
        for schema_name in actual_map:
            conn.execute(sql.SQL("CREATE SCHEMA {}").format(sql.Identifier(schema_name)))
        conn.commit()
    env = os.environ.copy()
    if parsed.get("password"):
        env["PGPASSWORD"] = parsed["password"]
    with tempfile.TemporaryDirectory(prefix="restore-schema-") as folder:
        raw_sql = Path(folder) / "restore.sql"
        isolated_sql = Path(folder) / "restore-isolated.sql"
        run([
            pg_restore,
            "--no-owner",
            "--no-privileges",
            "--schema=gerencial",
            "--schema=negocial",
            "--file", str(raw_sql),
            str(backup),
        ], env=env)
        _transform_restore_sql(raw_sql, isolated_sql, replacement_map)
        run([
            psql,
            "--host", parsed["host"],
            "--port", parsed["port"],
            "--username", parsed["username"],
            "--dbname", parsed["database"],
            "--set", "ON_ERROR_STOP=1",
            "--file", str(isolated_sql),
        ], env=env)
    return actual_map


def drop_validation_schemas(parsed: dict[str, str], schemas: list[str]) -> None:
    from psycopg import sql

    with connect(parsed, parsed["database"]) as conn:
        for schema_name in schemas:
            conn.execute(sql.SQL("DROP SCHEMA IF EXISTS {} CASCADE").format(sql.Identifier(schema_name)))
        conn.commit()

def validate(restored: dict[str, Any], source: dict[str, Any] | None) -> list[str]:
    errors: list[str] = []
    counts = restored["row_counts"]
    schemas = {name.split(".", 1)[0] for name in counts}
    if not {"gerencial", "negocial"}.issubset(schemas):
        errors.append("Schemas gerencial e negocial nao foram restaurados.")
    if len(counts) < 10:
        errors.append("Quantidade de tabelas restauradas abaixo do esperado.")
    if "negocial.producao_registros" not in counts:
        errors.append("Tabela central negocial.producao_registros ausente.")
    if source:
        missing = sorted(set(source["row_counts"]) - set(counts))
        extra = sorted(set(counts) - set(source["row_counts"]))
        mismatched = sorted(
            name for name, total in source["row_counts"].items()
            if name in counts and counts[name] != total
        )
        if missing:
            errors.append(f"Tabelas ausentes: {', '.join(missing)}")
        if extra:
            errors.append(f"Tabelas inesperadas: {', '.join(extra)}")
        if mismatched:
            errors.append(f"Contagens divergentes: {', '.join(mismatched)}")
        for key in ("views", "constraints", "indexes", "versions"):
            if restored[key] != source[key]:
                errors.append(f"Estrutura divergente em {key}.")
    return errors


def save_report(report: dict[str, Any]) -> Path:
    report_dir = settings.data_dir / "reports" / "database"
    report_dir.mkdir(parents=True, exist_ok=True)
    path = report_dir / f"restore_validation_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    path.write_text(json.dumps(report, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    return path


def main() -> int:
    parser = argparse.ArgumentParser(description="Restaura um dump em banco isolado e compara estrutura e dados.")
    parser.add_argument("backup", nargs="?", help="Dump existente; por padrao usa o mais recente.")
    parser.add_argument("--create", action="store_true", help="Cria dump consistente e valida contagens exatas.")
    args = parser.parse_args()

    service = DatabaseBackupService(settings.database_url, settings.data_dir)
    parsed = service._parsed()
    source_manifest: dict[str, Any] | None = None
    if args.create:
        backup, source_manifest = create_consistent_backup(service, parsed)
    else:
        backup = Path(args.backup).resolve() if args.backup else newest_backup(service)
    if not backup.exists():
        raise RuntimeError(f"Backup nao encontrado: {backup}")

    database_name = f"restore_validation_{uuid.uuid4().hex[:12]}"
    started = time.perf_counter()
    report: dict[str, Any] = {
        "ok": False,
        "started_at": datetime.now().isoformat(timespec="seconds"),
        "backup": backup.name,
        "backup_sha256": service._sha256(backup),
        "isolated_database": database_name,
    }
    created_database = False
    schema_map: dict[str, str] | None = None
    token = uuid.uuid4().hex[:10]
    try:
        try:
            create_validation_database(parsed, database_name)
            created_database = True
            report["isolation_mode"] = "temporary_database"
            restore(service, parsed, backup, database_name)
            with connect(parsed, database_name) as conn:
                restored_manifest = capture_manifest(conn)
        except Exception as create_error:
            from psycopg.errors import InsufficientPrivilege

            if not isinstance(create_error, InsufficientPrivilege):
                raise
            schema_map = {f"restore_g_{token}": "gerencial", f"restore_n_{token}": "negocial"}
            report["isolation_mode"] = "temporary_schemas"
            report["database_create_notice"] = "Usuario sem CREATEDB; validacao executada em schemas isolados."
            restore_into_isolated_schemas(service, parsed, backup, token)
            with connect(parsed, parsed["database"]) as conn:
                restored_manifest = capture_manifest(conn, schema_map)

        errors = validate(restored_manifest, source_manifest)
        report.update({
            "ok": not errors,
            "errors": errors,
            "tables": len(restored_manifest["row_counts"]),
            "rows": sum(restored_manifest["row_counts"].values()),
            "constraints": restored_manifest["constraints"],
            "indexes": restored_manifest["indexes"],
            "views": len(restored_manifest["views"]),
            "production_records": restored_manifest["row_counts"].get("negocial.producao_registros", 0),
            "exact_source_comparison": source_manifest is not None,
        })
        if errors:
            raise RuntimeError("; ".join(errors))
    except Exception as exc:
        report["error"] = str(exc)
        raise
    finally:
        report["elapsed_seconds"] = round(time.perf_counter() - started, 2)
        try:
            if created_database:
                drop_validation_database(parsed, database_name)
            elif schema_map:
                drop_validation_schemas(parsed, list(schema_map))
            report["isolated_environment_removed"] = True
        except Exception as exc:
            report["isolated_environment_removed"] = False
            report["cleanup_error"] = str(exc)
        report_path = save_report(report)
        report["report"] = str(report_path)
        print(json.dumps(report, ensure_ascii=False, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
