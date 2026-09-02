from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any, Iterable


ROOT = Path(__file__).resolve().parents[1]
PROJECT_ROOT = ROOT.parent
GERENCIAL_SQLITE = ROOT / "data" / "app.sqlite3"
NEGOCIAL_SQLITE = PROJECT_ROOT / "aplicacao-negocial" / "database" / "negocial.sqlite3"
SCHEMA_SQL = ROOT / "docs" / "postgres-schema.sql"


@dataclass
class MigrationReport:
    dry_run: bool
    counts: dict[str, int]
    skipped: dict[str, str]

    def add_count(self, table: str, count: int) -> None:
        self.counts[table] = count

    def add_skip(self, table: str, reason: str) -> None:
        self.skipped[table] = reason

    def print(self) -> None:
        mode = "DRY-RUN" if self.dry_run else "MIGRACAO"
        print(f"\n=== RELATORIO {mode} ===")
        for table, count in self.counts.items():
            print(f"{table}: {count}")
        if self.skipped:
            print("\nIgnorados:")
            for table, reason in self.skipped.items():
                print(f"{table}: {reason}")


def main() -> None:
    args = parse_args()
    report = MigrationReport(dry_run=args.dry_run, counts={}, skipped={})

    ensure_file(GERENCIAL_SQLITE)
    ensure_file(NEGOCIAL_SQLITE)
    ensure_file(SCHEMA_SQL)

    if args.dry_run:
        dry_run(report)
        report.print()
        return

    if not args.database_url:
        raise SystemExit("Informe --database-url ou use --dry-run.")

    migrate(args.database_url, report, reset=args.reset)
    report.print()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Migra SQLite Gerencial/Negocial para PostgreSQL.")
    parser.add_argument("--database-url", help="Ex: postgresql://usuario:senha@host:5432/projeto_negocial")
    parser.add_argument("--dry-run", action="store_true", help="Apenas le os SQLite e mostra contagens.")
    parser.add_argument("--reset", action="store_true", help="Limpa schemas gerencial/negocial antes de migrar.")
    return parser.parse_args()


def dry_run(report: MigrationReport) -> None:
    with sqlite_conn(NEGOCIAL_SQLITE) as negocial, sqlite_conn(GERENCIAL_SQLITE) as gerencial:
        validate_source_data(negocial, gerencial)
        for table in ["users", "producao_diaria", "pareceres", "sessions"]:
            count = count_rows(negocial, table)
            if table == "sessions":
                report.add_skip("negocial.sessions", f"{count} sessoes nao serao migradas")
            else:
                report.add_count(f"negocial.{table}", count)

        for table in [
            "users",
            "negociadores",
            "snapshots",
            "events",
            "overview_reads",
            "notification_reads",
            "notes",
            "sessions",
        ]:
            count = count_rows(gerencial, table)
            if table == "sessions":
                report.add_skip("gerencial.sessions", f"{count} sessoes nao serao migradas")
            else:
                report.add_count(f"gerencial.{table}", count)


def migrate(database_url: str, report: MigrationReport, reset: bool = False) -> None:
    try:
        import psycopg
        from psycopg.types.json import Jsonb
    except ImportError as exc:
        raise SystemExit("Instale psycopg[binary] para executar a migracao PostgreSQL.") from exc

    pg_url = normalize_postgres_url(database_url)
    with psycopg.connect(pg_url) as pg, sqlite_conn(NEGOCIAL_SQLITE) as negocial, sqlite_conn(GERENCIAL_SQLITE) as gerencial:
        validate_source_data(negocial, gerencial)
        with pg.cursor() as cur:
            if reset:
                cur.execute("DROP SCHEMA IF EXISTS gerencial CASCADE")
                cur.execute("DROP SCHEMA IF EXISTS negocial CASCADE")
            execute_schema(cur, SCHEMA_SQL.read_text(encoding="utf-8"))

        migrate_negocial(pg, negocial, Jsonb, report)
        migrate_gerencial(pg, gerencial, Jsonb, report)
        fix_sequences(pg)


def migrate_negocial(pg: Any, src: sqlite3.Connection, Jsonb: Any, report: MigrationReport) -> None:
    _ = Jsonb
    rows = fetch_all(src, "users")
    execute_many(
        pg,
        """
        INSERT INTO negocial.users (
            id, username, password_hash, role, active, carteira, meta_pagamento, created_at, updated_at
        )
        VALUES (%(id)s, %(username)s, %(password_hash)s, %(role)s, %(active)s, %(carteira)s,
                %(meta_pagamento)s, %(created_at)s, %(updated_at)s)
        ON CONFLICT (id) DO NOTHING
        """,
        [
            {
                **row,
                "role": normalize_role(row.get("role"), upper=True),
                "active": to_bool(row.get("active")),
                "carteira": normalize_carteira(row.get("carteira")),
                "meta_pagamento": to_decimal(row.get("meta_pagamento"), "70000.00"),
            }
            for row in rows
        ],
    )
    report.add_count("negocial.users", len(rows))

    rows = fetch_all(src, "producao_diaria")
    execute_many(
        pg,
        """
        INSERT INTO negocial.producao_diaria (
            id, data_acordo, npj, cliente, gecor, valor_total_acordo, valor_entrada, valor_ho,
            percentual_ho, tipo_acordo, data_vencimento, data_pagamento, status, justificativa_status,
            autorizacao_flexibilizacao, carteira, user_id, created_at, updated_at
        )
        VALUES (%(id)s, %(data_acordo)s, %(npj)s, %(cliente)s, %(gecor)s, %(valor_total_acordo)s,
                %(valor_entrada)s, %(valor_ho)s, %(percentual_ho)s, %(tipo_acordo)s,
                %(data_vencimento)s, %(data_pagamento)s, %(status)s, %(justificativa_status)s,
                %(autorizacao_flexibilizacao)s, %(carteira)s, %(user_id)s, %(created_at)s, %(updated_at)s)
        ON CONFLICT (id) DO NOTHING
        """,
        [
            {
                **row,
                "carteira": normalize_carteira(row.get("carteira")) or "GAMMA",
                "valor_total_acordo": to_decimal(row.get("valor_total_acordo")),
                "valor_entrada": to_decimal(row.get("valor_entrada")),
                "valor_ho": to_decimal(row.get("valor_ho")),
                "percentual_ho": to_decimal(row.get("percentual_ho")),
            }
            for row in rows
        ],
    )
    report.add_count("negocial.producao_diaria", len(rows))

    rows = fetch_all(src, "pareceres")
    execute_many(
        pg,
        """
        INSERT INTO negocial.pareceres (
            id, data_solicitacao, data_conclusao, npj, cliente, motivo, descricao,
            status, carteira, user_id, created_at, updated_at
        )
        VALUES (%(id)s, %(data_solicitacao)s, %(data_conclusao)s, %(npj)s, %(cliente)s,
                %(motivo)s, %(descricao)s, %(status)s, %(carteira)s, %(user_id)s,
                %(created_at)s, %(updated_at)s)
        ON CONFLICT (id) DO NOTHING
        """,
        [{**row, "carteira": normalize_carteira(row.get("carteira")) or "GAMMA"} for row in rows],
    )
    report.add_count("negocial.pareceres", len(rows))
    report.add_skip("negocial.sessions", f"{count_rows(src, 'sessions')} sessoes nao migradas")


def migrate_gerencial(pg: Any, src: sqlite3.Connection, Jsonb: Any, report: MigrationReport) -> None:
    rows = fetch_all(src, "users")
    execute_many(
        pg,
        """
        INSERT INTO gerencial.users (
            id, username, password_hash, salt, role, active, created_at, updated_at
        )
        VALUES (%(id)s, %(username)s, %(password_hash)s, %(salt)s, %(role)s, %(active)s,
                %(created_at)s, %(updated_at)s)
        ON CONFLICT (id) DO NOTHING
        """,
        [{**row, "role": normalize_role(row.get("role"), upper=False), "active": to_bool(row.get("active"))} for row in rows],
    )
    report.add_count("gerencial.users", len(rows))

    rows = fetch_all(src, "negociadores")
    execute_many(
        pg,
        """
        INSERT INTO gerencial.negociadores (
            id, nome, carteira, arquivo_path, sheet, senha, source_type, negocial_user_id,
            negocial_username, meta_pagamento, active, last_mtime, created_at, updated_at
        )
        VALUES (%(id)s, %(nome)s, %(carteira)s, %(arquivo_path)s, %(sheet)s, %(senha)s,
                %(source_type)s, %(negocial_user_id)s, %(negocial_username)s, %(meta_pagamento)s,
                %(active)s, %(last_mtime)s, %(created_at)s, %(updated_at)s)
        ON CONFLICT (id) DO NOTHING
        """,
        [
            {
                **row,
                "carteira": normalize_carteira(row.get("carteira")),
                "source_type": row.get("source_type") or "planilha",
                "active": to_bool(row.get("active")),
                "last_mtime": to_float_or_none(row.get("last_mtime")),
                "meta_pagamento": to_decimal(row.get("meta_pagamento"), none_if_empty=True),
            }
            for row in rows
        ],
    )
    report.add_count("gerencial.negociadores", len(rows))

    rows = fetch_all(src, "snapshots")
    execute_many(
        pg,
        """
        INSERT INTO gerencial.snapshots (id, negociador_id, sheet, captured_at, content_json)
        VALUES (%(id)s, %(negociador_id)s, %(sheet)s, %(captured_at)s, %(content_json)s)
        ON CONFLICT (id) DO NOTHING
        """,
        [{**row, "content_json": Jsonb(parse_json(row.get("content_json")))} for row in rows],
    )
    report.add_count("gerencial.snapshots", len(rows))

    rows = fetch_all(src, "events")
    execute_many(
        pg,
        """
        INSERT INTO gerencial.events (
            id, negociador_id, snapshot_before_id, snapshot_after_id, event_type, sheet,
            file_path, changed_at, changes_count, delta_json, metadata_json
        )
        VALUES (%(id)s, %(negociador_id)s, %(snapshot_before_id)s, %(snapshot_after_id)s,
                %(event_type)s, %(sheet)s, %(file_path)s, %(changed_at)s, %(changes_count)s,
                %(delta_json)s, %(metadata_json)s)
        ON CONFLICT (id) DO NOTHING
        """,
        [
            {
                **row,
                "delta_json": Jsonb(parse_json(row.get("delta_json"))),
                "metadata_json": Jsonb(parse_json(row.get("metadata_json"))),
            }
            for row in rows
        ],
    )
    report.add_count("gerencial.events", len(rows))

    for table in ["overview_reads", "notification_reads", "notes"]:
        rows = fetch_all(src, table)
        insert_simple_gerencial(pg, table, rows)
        report.add_count(f"gerencial.{table}", len(rows))
    report.add_skip("gerencial.sessions", f"{count_rows(src, 'sessions')} sessoes nao migradas")


def insert_simple_gerencial(pg: Any, table: str, rows: list[dict[str, Any]]) -> None:
    if not rows:
        return
    columns = list(rows[0].keys())
    column_sql = ", ".join(columns)
    values_sql = ", ".join([f"%({column})s" for column in columns])
    sql = f"INSERT INTO gerencial.{table} ({column_sql}) VALUES ({values_sql}) ON CONFLICT DO NOTHING"
    execute_many(pg, sql, rows)


def fix_sequences(pg: Any) -> None:
    sequence_targets = [
        ("negocial", "users"),
        ("negocial", "sessions"),
        ("negocial", "producao_diaria"),
        ("negocial", "pareceres"),
        ("gerencial", "users"),
        ("gerencial", "negociadores"),
        ("gerencial", "snapshots"),
        ("gerencial", "events"),
        ("gerencial", "overview_reads"),
        ("gerencial", "notification_reads"),
        ("gerencial", "notes"),
    ]
    with pg.cursor() as cur:
        for schema, table in sequence_targets:
            cur.execute(
                f"""
                SELECT setval(
                    pg_get_serial_sequence(%s, 'id'),
                    COALESCE((SELECT MAX(id) FROM {quote_ident(schema)}.{quote_ident(table)}), 1),
                    true
                )
                """,
                (f"{schema}.{table}",),
            )


def validate_source_data(negocial: sqlite3.Connection, gerencial: sqlite3.Connection) -> None:
    allowed_carteiras = {"GAMMA", "ALPHA", "BETA", None}
    allowed_producao_status = {
        "AGUARDANDO_PAGAMENTO",
        "PAGAMENTO_REALIZADO",
        "PROPOSTA",
        "PROPOSTA_NEGADA",
        "QUEBRA",
    }
    allowed_tipo_acordo = {"A_VISTA", "PARCELADO"}
    allowed_parecer_status = {"PENDENTE", "SOLICITADO", "CANCELADO"}
    allowed_motivos = {"PISO NEGOCIAL", "PARECER", "REUNIAO"}

    errors: list[str] = []
    errors += invalid_values(negocial, "users", "carteira", allowed_carteiras, normalize_carteira, "negocial.users")
    errors += invalid_values(negocial, "producao_diaria", "carteira", allowed_carteiras - {None}, normalize_carteira, "negocial.producao_diaria")
    errors += invalid_values(negocial, "producao_diaria", "status", allowed_producao_status, clean_text, "negocial.producao_diaria")
    errors += invalid_values(negocial, "producao_diaria", "tipo_acordo", allowed_tipo_acordo, clean_text, "negocial.producao_diaria")
    errors += invalid_values(negocial, "pareceres", "carteira", allowed_carteiras - {None}, normalize_carteira, "negocial.pareceres")
    errors += invalid_values(negocial, "pareceres", "status", allowed_parecer_status, clean_text, "negocial.pareceres")
    errors += invalid_values(negocial, "pareceres", "motivo", allowed_motivos, clean_text, "negocial.pareceres")
    errors += invalid_values(gerencial, "negociadores", "carteira", allowed_carteiras, normalize_carteira, "gerencial.negociadores")

    negocial_ids = {row["id"] for row in fetch_all(negocial, "users")}
    missing_negocial_links = [
        row for row in fetch_all(gerencial, "negociadores")
        if row.get("negocial_user_id") is not None and row.get("negocial_user_id") not in negocial_ids
    ]
    if missing_negocial_links:
        ids = ", ".join(str(row["id"]) for row in missing_negocial_links[:10])
        errors.append(f"gerencial.negociadores possui negocial_user_id sem usuario correspondente: ids {ids}")

    if errors:
        joined = "\n- ".join(errors)
        raise SystemExit(f"Validacao da origem falhou:\n- {joined}")


def execute_many(pg: Any, sql: str, rows: Iterable[dict[str, Any]]) -> None:
    rows = list(rows)
    if not rows:
        return
    with pg.cursor() as cur:
        cur.executemany(sql, rows)


def execute_schema(cur: Any, sql: str) -> None:
    for statement in sql.split(";"):
        cleaned = statement.strip()
        if not cleaned or cleaned.upper() in {"BEGIN", "COMMIT"}:
            continue
        cur.execute(cleaned)


def sqlite_conn(path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    return conn


def fetch_all(conn: sqlite3.Connection, table: str) -> list[dict[str, Any]]:
    return [dict(row) for row in conn.execute(f'SELECT * FROM "{table}"').fetchall()]


def count_rows(conn: sqlite3.Connection, table: str) -> int:
    return int(conn.execute(f'SELECT COUNT(*) FROM "{table}"').fetchone()[0])


def invalid_values(
    conn: sqlite3.Connection,
    table: str,
    column: str,
    allowed: set[Any],
    normalizer: Any,
    label: str,
) -> list[str]:
    invalid: list[str] = []
    rows = conn.execute(f'SELECT DISTINCT "{column}" AS value FROM "{table}"').fetchall()
    for row in rows:
        normalized = normalizer(row["value"])
        if normalized not in allowed:
            invalid.append(f"{label}.{column}: valor invalido {row['value']!r} normalizado para {normalized!r}")
    return invalid


def ensure_file(path: Path) -> None:
    if not path.exists():
        raise SystemExit(f"Arquivo nao encontrado: {path}")


def normalize_postgres_url(database_url: str) -> str:
    return (
        database_url.replace("postgresql+psycopg://", "postgresql://", 1)
        .replace("postgresql+psycopg2://", "postgresql://", 1)
    )


def normalize_carteira(value: Any) -> str | None:
    if value is None:
        return None
    normalized = str(value).strip().upper()
    if not normalized:
        return None
    if normalized == "ALPHA":
        return "ALPHA"
    if normalized in {"GAMMA", "BETA"}:
        return normalized
    return normalized


def clean_text(value: Any) -> str | None:
    if value is None:
        return None
    return str(value).strip()


def normalize_role(value: Any, upper: bool) -> str:
    role = str(value or ("USER" if upper else "user")).strip()
    return role.upper() if upper else role.lower()


def to_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() not in {"0", "false", "none", ""}


def to_decimal(value: Any, default: str | None = "0", none_if_empty: bool = False) -> Decimal | None:
    if value is None or value == "":
        return None if none_if_empty else Decimal(default or "0")
    return Decimal(str(value))


def to_float_or_none(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def parse_json(value: Any) -> Any:
    if value is None:
        return None
    if isinstance(value, str):
        return json.loads(value)
    return value


def quote_ident(value: str) -> str:
    return '"' + value.replace('"', '""') + '"'


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        sys.exit(130)
