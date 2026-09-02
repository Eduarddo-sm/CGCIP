from __future__ import annotations

import json
import os
import secrets
import sqlite3
import threading
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from database.auth_repository import AuthRepository
from database.connection import DatabaseConnection, NoOpLock
from database.permissions import DEFAULT_ROLE_PERMISSIONS, GERENCIAL_SCHEMA, PERMISSION_LABELS
from services.credential_cipher import CredentialCipher
from services.schema_migration import run_schema_migrations


class Repository:
    def __init__(self, database_url: str | Path) -> None:
        self.database_url = self._normalize_database_url(database_url)
        self.backend = self._detect_backend(self.database_url)
        self.db_path = self._sqlite_path(self.database_url) if self.backend == "sqlite" else None
        self.lock = threading.RLock() if self.backend == "sqlite" else NoOpLock()
        if self.backend == "postgresql":
            run_schema_migrations(self.database_url)
        self.pool = self._create_postgres_pool() if self.backend == "postgresql" else None
        self.pool_timeout = float(os.environ.get("GERENCIAL_DB_POOL_TIMEOUT", "10"))
        self._snapshot_content_cache: dict[int, dict[str, Any]] = {}
        self.credentials = CredentialCipher()
        if self.db_path:
            self.db_path.parent.mkdir(exist_ok=True)
        self.init_schema()
        self.auth = AuthRepository(self.connect, self.lock)

    def connect(self) -> DatabaseConnection:
        if self.backend == "sqlite":
            conn = sqlite3.connect(self.db_path, check_same_thread=False)
            conn.row_factory = sqlite3.Row
            return DatabaseConnection(conn, self.backend)
        if self.pool is not None:
            return DatabaseConnection(
                None,
                self.backend,
                owner_context=self.pool.connection(timeout=self.pool_timeout),
            )
        raise RuntimeError("Pool PostgreSQL nao inicializado.")

    def _create_postgres_pool(self):
        try:
            from psycopg.rows import dict_row
            from psycopg_pool import ConnectionPool
        except ImportError as exc:
            raise RuntimeError("Para usar PostgreSQL no gerencial, instale psycopg[binary,pool].") from exc

        # Dimensionado para a operacao atual (cerca de 25 usuarios simultaneos)
        # sem abrir uma conexao por usuario.
        min_size = max(1, int(os.environ.get("GERENCIAL_DB_POOL_MIN", "4")))
        max_size = max(min_size, int(os.environ.get("GERENCIAL_DB_POOL_MAX", "16")))
        timeout = max(1.0, float(os.environ.get("GERENCIAL_DB_POOL_TIMEOUT", "10")))
        pool = ConnectionPool(
            conninfo=self.database_url,
            min_size=min_size,
            max_size=max_size,
            timeout=timeout,
            kwargs={"row_factory": dict_row},
            configure=self._configure_postgres_connection,
            name="gerencial",
            open=False,
        )
        pool.open(wait=True, timeout=timeout)
        return pool

    @staticmethod
    def _configure_postgres_connection(conn: Any) -> None:
        conn.execute(f"SET search_path TO {GERENCIAL_SCHEMA}, public")
        conn.commit()

    def close(self) -> None:
        if self.pool is not None:
            self.pool.close()

    def pool_stats(self) -> dict[str, Any]:
        return dict(self.pool.get_stats()) if self.pool is not None else {}

    def init_schema(self) -> None:
        with self.lock, self.connect() as conn:
            if self.backend == "postgresql":
                self._seed_postgres_data(conn)
                self._bootstrap_admin(conn)
                return
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS negociadores (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    nome TEXT NOT NULL,
                    carteira TEXT,
                    arquivo_path TEXT NOT NULL,
                    sheet TEXT NOT NULL,
                    senha TEXT,
                    source_type TEXT NOT NULL DEFAULT 'planilha',
                    negocial_user_id INTEGER,
                    negocial_username TEXT,
                    meta_pagamento REAL,
                    active INTEGER NOT NULL DEFAULT 1,
                    last_mtime REAL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS carteiras (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    nome TEXT NOT NULL UNIQUE,
                    descricao TEXT,
                    active INTEGER NOT NULL DEFAULT 1,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS snapshots (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    negociador_id INTEGER NOT NULL,
                    sheet TEXT NOT NULL,
                    captured_at TEXT NOT NULL,
                    content_json TEXT NOT NULL,
                    FOREIGN KEY (negociador_id) REFERENCES negociadores(id)
                );

                CREATE TABLE IF NOT EXISTS events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    negociador_id INTEGER NOT NULL,
                    snapshot_before_id INTEGER,
                    snapshot_after_id INTEGER NOT NULL,
                    event_type TEXT NOT NULL,
                    sheet TEXT NOT NULL,
                    file_path TEXT NOT NULL,
                    changed_at TEXT NOT NULL,
                    changes_count INTEGER NOT NULL,
                    delta_json TEXT NOT NULL,
                    metadata_json TEXT NOT NULL,
                    FOREIGN KEY (negociador_id) REFERENCES negociadores(id)
                );

                CREATE TABLE IF NOT EXISTS overview_reads (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    event_id INTEGER NOT NULL,
                    change_index INTEGER NOT NULL,
                    usuario TEXT NOT NULL,
                    read_at TEXT NOT NULL,
                    UNIQUE(event_id, change_index, usuario),
                    FOREIGN KEY (event_id) REFERENCES events(id)
                );

                CREATE TABLE IF NOT EXISTS notification_reads (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    notification_id TEXT NOT NULL,
                    usuario TEXT NOT NULL,
                    read_at TEXT NOT NULL,
                    UNIQUE(notification_id, usuario)
                );

                CREATE TABLE IF NOT EXISTS notes (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    target_type TEXT NOT NULL,
                    target_id TEXT NOT NULL,
                    text TEXT NOT NULL,
                    usuario TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS users (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    username TEXT NOT NULL UNIQUE,
                    password_hash TEXT NOT NULL,
                    salt TEXT NOT NULL,
                    role TEXT NOT NULL DEFAULT 'user',
                    active INTEGER NOT NULL DEFAULT 1,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS sessions (
                    token TEXT PRIMARY KEY,
                    user_id INTEGER NOT NULL,
                    created_at TEXT NOT NULL,
                    expires_at TEXT NOT NULL,
                    FOREIGN KEY (user_id) REFERENCES users(id)
                );

                CREATE TABLE IF NOT EXISTS general_audit (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    actor TEXT,
                    actor_role TEXT,
                    action TEXT NOT NULL,
                    entity_type TEXT NOT NULL,
                    entity_id TEXT,
                    entity_label TEXT,
                    outcome TEXT NOT NULL DEFAULT 'success',
                    details_json TEXT NOT NULL,
                    ip_address TEXT,
                    created_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS role_permissions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    role TEXT NOT NULL,
                    permission TEXT NOT NULL,
                    allowed INTEGER NOT NULL DEFAULT 0,
                    updated_at TEXT NOT NULL,
                    UNIQUE(role, permission)
                );

                CREATE TABLE IF NOT EXISTS user_permissions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    permission TEXT NOT NULL,
                    allowed INTEGER NOT NULL DEFAULT 0,
                    updated_at TEXT NOT NULL,
                    UNIQUE(user_id, permission),
                    FOREIGN KEY (user_id) REFERENCES users(id)
                );

                CREATE TABLE IF NOT EXISTS protocolos (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    row_key INTEGER NOT NULL UNIQUE,
                    data_mes TEXT,
                    carteira TEXT,
                    nome TEXT,
                    pj TEXT,
                    processo TEXT,
                    data_solicitacao TEXT,
                    status TEXT NOT NULL DEFAULT 'PENDENTE',
                    data_conclusao TEXT,
                    observacao TEXT,
                    extra_json TEXT,
                    source TEXT NOT NULL DEFAULT 'database',
                    created_by TEXT,
                    updated_by TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS colchao_alpha (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    sheet_name TEXT NOT NULL,
                    row_number INTEGER NOT NULL,
                    identifier TEXT,
                    cliente TEXT,
                    cpf_cnpj TEXT,
                    acordo TEXT,
                    parcela TEXT,
                    valor REAL,
                    vencimento TEXT,
                    status TEXT,
                    observacao TEXT,
                    operador TEXT,
                    bucket TEXT,
                    raw_json TEXT NOT NULL,
                    active INTEGER NOT NULL DEFAULT 1,
                    source_updated_at TEXT,
                    updated_by TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    UNIQUE(sheet_name, row_number)
                );

                CREATE TABLE IF NOT EXISTS colchao_beta (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    sheet_name TEXT NOT NULL,
                    row_number INTEGER NOT NULL,
                    identifier TEXT,
                    cliente TEXT,
                    cpf_cnpj TEXT,
                    acordo TEXT,
                    parcela TEXT,
                    valor REAL,
                    vencimento TEXT,
                    status TEXT,
                    observacao TEXT,
                    operador TEXT,
                    bucket TEXT,
                    raw_json TEXT NOT NULL,
                    active INTEGER NOT NULL DEFAULT 1,
                    source_updated_at TEXT,
                    updated_by TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    UNIQUE(sheet_name, row_number)
                );

                CREATE TABLE IF NOT EXISTS colchao_acordos (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    carteira TEXT NOT NULL,
                    source_sheet TEXT NOT NULL DEFAULT '',
                    identifier TEXT NOT NULL,
                    agreement_number TEXT NOT NULL,
                    cliente TEXT,
                    cpf_cnpj TEXT,
                    operador TEXT,
                    tipo_acordo TEXT,
                    metadata_json TEXT NOT NULL DEFAULT '{}',
                    active INTEGER NOT NULL DEFAULT 1,
                    source TEXT NOT NULL DEFAULT 'database',
                    created_by TEXT,
                    updated_by TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    UNIQUE(carteira, source_sheet, identifier, agreement_number)
                );

                CREATE TABLE IF NOT EXISTS colchao_parcelas (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    acordo_id INTEGER NOT NULL,
                    carteira TEXT NOT NULL,
                    source_sheet TEXT NOT NULL DEFAULT '',
                    source_row INTEGER NOT NULL,
                    parcela TEXT,
                    valor REAL,
                    vencimento TEXT,
                    status TEXT NOT NULL DEFAULT 'A VENCER',
                    observacao TEXT,
                    bucket TEXT,
                    raw_json TEXT NOT NULL DEFAULT '{}',
                    active INTEGER NOT NULL DEFAULT 1,
                    source_updated_at TEXT,
                    updated_by TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    UNIQUE(carteira, source_sheet, source_row),
                    FOREIGN KEY (acordo_id) REFERENCES colchao_acordos(id) ON DELETE CASCADE
                );

                CREATE TABLE IF NOT EXISTS colchao_configuracoes (
                    carteira TEXT PRIMARY KEY,
                    version INTEGER NOT NULL DEFAULT 1,
                    config_json TEXT NOT NULL DEFAULT '{}',
                    updated_by TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS colchao_configuracao_versions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    carteira TEXT NOT NULL,
                    version INTEGER NOT NULL,
                    config_json TEXT NOT NULL,
                    created_by TEXT,
                    created_at TEXT NOT NULL,
                    UNIQUE(carteira, version)
                );
                """
            )
            self._ensure_column(conn, "negociadores", "carteira", "TEXT")
            self._ensure_column(conn, "negociadores", "source_type", "TEXT")
            self._ensure_column(conn, "negociadores", "negocial_user_id", "INTEGER")
            self._ensure_column(conn, "negociadores", "negocial_username", "TEXT")
            self._ensure_column(conn, "negociadores", "meta_pagamento", "REAL")
            conn.execute("UPDATE negociadores SET source_type = 'planilha' WHERE source_type IS NULL OR source_type = ''")
            self._seed_default_carteiras(conn)
            self._ensure_role_permissions(conn)
            self._ensure_governance_schema(conn)
            self._bootstrap_admin(conn)

    def _bootstrap_admin(self, conn: DatabaseConnection) -> None:
        username = os.environ.get("GERENCIAL_BOOTSTRAP_ADMIN_USERNAME", "").strip()
        password = os.environ.get("GERENCIAL_BOOTSTRAP_ADMIN_PASSWORD", "")
        existing = conn.execute("SELECT COUNT(*) AS total FROM users").fetchone()
        total = int(existing["total"] if isinstance(existing, dict) else existing[0])
        if total:
            return
        if not username and not password:
            if self.backend == "postgresql":
                raise RuntimeError(
                    "Banco gerencial sem usuarios. Defina GERENCIAL_BOOTSTRAP_ADMIN_USERNAME e "
                    "GERENCIAL_BOOTSTRAP_ADMIN_PASSWORD apenas para o primeiro bootstrap."
                )
            return
        if not username or len(password) < 12 or password in {"2024", "admin", "password", username}:
            raise RuntimeError("Credenciais de bootstrap gerencial ausentes ou inseguras.")
        self._ensure_user_conn(conn, username, password, "superadmin")

    def _seed_postgres_data(self, conn: DatabaseConnection) -> None:
        conn.execute("UPDATE negociadores SET source_type = 'planilha' WHERE source_type IS NULL OR source_type = ''")
        self._seed_default_carteiras(conn)
        self._ensure_role_permissions(conn)
        self._seed_retention_policies(conn)

    def _ensure_governance_schema(self, conn: DatabaseConnection) -> None:
        if self.backend == "postgresql":
            return
        if self.backend == "postgresql":
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS db_retention_policies (
                    scope TEXT PRIMARY KEY,
                    retention_days INTEGER NOT NULL,
                    keep_latest INTEGER NOT NULL DEFAULT 0,
                    enabled BOOLEAN NOT NULL DEFAULT TRUE,
                    updated_at TIMESTAMPTZ NOT NULL
                );

                CREATE TABLE IF NOT EXISTS data_quality_issues (
                    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
                    schema_name TEXT NOT NULL,
                    table_name TEXT NOT NULL,
                    entity_id TEXT,
                    issue_type TEXT NOT NULL,
                    severity TEXT NOT NULL DEFAULT 'warning',
                    details_json JSONB NOT NULL,
                    resolved BOOLEAN NOT NULL DEFAULT FALSE,
                    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                    resolved_at TIMESTAMPTZ
                );

                CREATE TABLE IF NOT EXISTS database_health_snapshots (
                    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
                    captured_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                    database_size_bytes BIGINT NOT NULL,
                    max_connections INTEGER NOT NULL,
                    total_connections INTEGER NOT NULL,
                    active_connections INTEGER NOT NULL,
                    idle_connections INTEGER NOT NULL,
                    cache_hit_percent NUMERIC(7,2) NOT NULL,
                    transactions_committed BIGINT NOT NULL,
                    transactions_rolled_back BIGINT NOT NULL,
                    deadlocks BIGINT NOT NULL,
                    temp_bytes BIGINT NOT NULL,
                    waiting_locks INTEGER NOT NULL,
                    long_transactions INTEGER NOT NULL,
                    slowest_transaction_seconds NUMERIC(12,2) NOT NULL,
                    pool_stats_json JSONB NOT NULL DEFAULT '{}'::jsonb,
                    alerts_json JSONB NOT NULL DEFAULT '[]'::jsonb
                );

                CREATE TABLE IF NOT EXISTS database_table_growth_snapshots (
                    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
                    health_snapshot_id BIGINT NOT NULL REFERENCES database_health_snapshots(id) ON DELETE CASCADE,
                    schema_name TEXT NOT NULL,
                    table_name TEXT NOT NULL,
                    row_estimate BIGINT NOT NULL,
                    dead_rows BIGINT NOT NULL,
                    size_bytes BIGINT NOT NULL,
                    growth_bytes BIGINT NOT NULL DEFAULT 0,
                    growth_percent NUMERIC(12,2) NOT NULL DEFAULT 0,
                    captured_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                    UNIQUE (health_snapshot_id, schema_name, table_name)
                );
                """
            )
        else:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS db_retention_policies (
                    scope TEXT PRIMARY KEY,
                    retention_days INTEGER NOT NULL,
                    keep_latest INTEGER NOT NULL DEFAULT 0,
                    enabled INTEGER NOT NULL DEFAULT 1,
                    updated_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS data_quality_issues (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    schema_name TEXT NOT NULL,
                    table_name TEXT NOT NULL,
                    entity_id TEXT,
                    issue_type TEXT NOT NULL,
                    severity TEXT NOT NULL DEFAULT 'warning',
                    details_json TEXT NOT NULL,
                    resolved INTEGER NOT NULL DEFAULT 0,
                    created_at TEXT NOT NULL,
                    resolved_at TEXT
                );

                CREATE TABLE IF NOT EXISTS database_health_snapshots (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    captured_at TEXT NOT NULL,
                    database_size_bytes INTEGER NOT NULL,
                    max_connections INTEGER NOT NULL,
                    total_connections INTEGER NOT NULL,
                    active_connections INTEGER NOT NULL,
                    idle_connections INTEGER NOT NULL,
                    cache_hit_percent REAL NOT NULL,
                    transactions_committed INTEGER NOT NULL,
                    transactions_rolled_back INTEGER NOT NULL,
                    deadlocks INTEGER NOT NULL,
                    temp_bytes INTEGER NOT NULL,
                    waiting_locks INTEGER NOT NULL,
                    long_transactions INTEGER NOT NULL,
                    slowest_transaction_seconds REAL NOT NULL,
                    pool_stats_json TEXT NOT NULL,
                    alerts_json TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS database_table_growth_snapshots (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    health_snapshot_id INTEGER NOT NULL REFERENCES database_health_snapshots(id) ON DELETE CASCADE,
                    schema_name TEXT NOT NULL,
                    table_name TEXT NOT NULL,
                    row_estimate INTEGER NOT NULL,
                    dead_rows INTEGER NOT NULL,
                    size_bytes INTEGER NOT NULL,
                    growth_bytes INTEGER NOT NULL DEFAULT 0,
                    growth_percent REAL NOT NULL DEFAULT 0,
                    captured_at TEXT NOT NULL,
                    UNIQUE (health_snapshot_id, schema_name, table_name)
                );
                """
            )
        conn.executescript(
            """
            CREATE INDEX IF NOT EXISTS ix_gerencial_data_quality_open
                ON data_quality_issues(resolved, severity, created_at DESC);
            CREATE INDEX IF NOT EXISTS ix_gerencial_data_quality_entity
                ON data_quality_issues(schema_name, table_name, entity_id);
            CREATE INDEX IF NOT EXISTS ix_gerencial_database_health_captured
                ON database_health_snapshots(captured_at DESC);
            CREATE INDEX IF NOT EXISTS ix_gerencial_database_growth_table_date
                ON database_table_growth_snapshots(schema_name, table_name, captured_at DESC);
            CREATE INDEX IF NOT EXISTS ix_gerencial_sessions_expires_at ON sessions(expires_at);
            CREATE INDEX IF NOT EXISTS ix_gerencial_events_type_date ON events(event_type, changed_at DESC);
            CREATE INDEX IF NOT EXISTS ix_gerencial_events_sheet_date ON events(sheet, changed_at DESC);
            CREATE INDEX IF NOT EXISTS ix_gerencial_protocolos_carteira_status ON protocolos(carteira, status);
            CREATE INDEX IF NOT EXISTS ix_gerencial_colchao_alpha_active_status ON colchao_alpha(active, status);
            CREATE INDEX IF NOT EXISTS ix_gerencial_colchao_beta_active_status ON colchao_beta(active, status);
            """
        )
        now = datetime.now().isoformat(timespec="seconds")
        defaults = (
            ("snapshots", 120, 5000),
            ("reads", 180, 0),
            ("sessions", 7, 0),
            ("audit", 365, 0),
            ("backups", 90, 30),
            ("monitoring", 90, 0),
        )
        for scope, retention_days, keep_latest in defaults:
            current = conn.execute("SELECT scope FROM db_retention_policies WHERE scope = ?", (scope,)).fetchone()
            if current:
                continue
            conn.execute(
                """
                INSERT INTO db_retention_policies (scope, retention_days, keep_latest, enabled, updated_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (scope, retention_days, keep_latest, True, now),
            )
    def _seed_retention_policies(self, conn: DatabaseConnection) -> None:
        now = datetime.now().isoformat(timespec="seconds")
        defaults = (
            ("snapshots", 120, 5000),
            ("reads", 180, 0),
            ("sessions", 7, 0),
            ("audit", 365, 0),
            ("backups", 90, 30),
            ("monitoring", 90, 0),
        )
        for scope, retention_days, keep_latest in defaults:
            current = conn.execute("SELECT scope FROM db_retention_policies WHERE scope = ?", (scope,)).fetchone()
            if current:
                continue
            conn.execute(
                """
                INSERT INTO db_retention_policies (scope, retention_days, keep_latest, enabled, updated_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (scope, retention_days, keep_latest, True, now),
            )

    def _seed_default_carteiras(self, conn: DatabaseConnection) -> None:
        now = datetime.now().isoformat(timespec="seconds")
        for nome in ("GAMMA", "ALPHA", "BETA"):
            existing = conn.execute("SELECT id FROM carteiras WHERE upper(nome) = upper(?)", (nome,)).fetchone()
            if existing:
                continue
            conn.execute(
                """
                INSERT INTO carteiras (nome, descricao, active, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (nome, "", True, now, now),
            )

    def _ensure_role_permissions(self, conn: DatabaseConnection) -> None:
        now = datetime.now().isoformat(timespec="seconds")
        for role, permissions in DEFAULT_ROLE_PERMISSIONS.items():
            for permission, allowed in permissions.items():
                current = conn.execute(
                    "SELECT id FROM role_permissions WHERE role = ? AND permission = ?",
                    (role, permission),
                ).fetchone()
                if current:
                    continue
                conn.execute(
                    """
                    INSERT INTO role_permissions (role, permission, allowed, updated_at)
                    VALUES (?, ?, ?, ?)
                    """,
                    (role, permission, bool(allowed), now),
                )

    def _ensure_column(self, conn: DatabaseConnection, table: str, column: str, definition: str) -> None:
        if self.backend == "postgresql":
            rows = conn.execute(
                """
                SELECT column_name AS name
                FROM information_schema.columns
                WHERE table_schema = %s AND table_name = %s
                """,
                (GERENCIAL_SCHEMA, table),
            ).fetchall()
            columns = [row["name"] for row in rows]
        else:
            columns = [row["name"] for row in conn.execute(f"PRAGMA table_info({table})").fetchall()]
        if column not in columns:
            conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")

    def _insert_returning_id(self, conn: DatabaseConnection, sql: str, params: tuple[Any, ...]) -> int:
        if self.backend == "postgresql":
            row = conn.execute(f"{sql} RETURNING id", params).fetchone()
            return int(row["id"])
        cur = conn.execute(sql, params)
        return int(cur.lastrowid)

    def _normalize_database_url(self, database_url: str | Path) -> str:
        if isinstance(database_url, Path):
            return f"sqlite:///{database_url.as_posix()}"
        if "://" not in database_url:
            return f"sqlite:///{Path(database_url).as_posix()}"
        if database_url.startswith("postgresql+psycopg://"):
            return database_url.replace("postgresql+psycopg://", "postgresql://", 1)
        if database_url.startswith("postgresql+psycopg2://"):
            return database_url.replace("postgresql+psycopg2://", "postgresql://", 1)
        return database_url

    def _detect_backend(self, database_url: str) -> str:
        scheme = urlparse(database_url).scheme
        if scheme.startswith("sqlite"):
            return "sqlite"
        if scheme.startswith(("postgresql", "postgres")):
            return "postgresql"
        raise ValueError(f"Banco nao suportado: {scheme}")

    def _sqlite_path(self, database_url: str) -> Path:
        path = database_url.replace("sqlite:///", "", 1)
        return Path(path)

    def list_carteiras(self, include_inactive: bool = False) -> list[dict[str, Any]]:
        with self.lock, self.connect() as conn:
            registered_filter = "" if include_inactive else "WHERE active = 1"
            registered = conn.execute(
                f"""
                SELECT id, nome, descricao, active, created_at, updated_at
                FROM carteiras
                {registered_filter}
                ORDER BY nome
                """
            ).fetchall()
            counts = conn.execute(
                """
                SELECT carteira, COUNT(*) AS total
                FROM negociadores
                WHERE active = 1 AND carteira IS NOT NULL AND trim(carteira) <> ''
                GROUP BY carteira
                """
            ).fetchall()

        by_name: dict[str, dict[str, Any]] = {}
        for row in registered:
            item = dict(row)
            nome = self._normalize_carteira_nome(item.get("nome"))
            if not nome:
                continue
            item["nome"] = nome
            item["negociadores"] = 0
            item["registered"] = True
            by_name[nome] = item

        for row in counts:
            carteira = self._normalize_carteira_nome(row["carteira"])
            if not carteira:
                continue
            item = by_name.setdefault(
                carteira,
                {
                    "id": None,
                    "nome": carteira,
                    "descricao": "",
                    "active": True,
                    "created_at": "",
                    "updated_at": "",
                    "registered": False,
                    "negociadores": 0,
                },
            )
            item["negociadores"] = int(row["total"] or 0)

        return sorted(by_name.values(), key=lambda item: str(item["nome"]).lower())

    def create_carteira(self, nome: str, descricao: str = "") -> dict[str, Any]:
        carteira = self._normalize_carteira_nome(nome)
        if not carteira:
            raise ValueError("Nome da carteira obrigatorio.")
        now = datetime.now().isoformat(timespec="seconds")
        with self.lock, self.connect() as conn:
            current = conn.execute("SELECT * FROM carteiras WHERE upper(nome) = upper(?)", (carteira,)).fetchone()
            if current:
                conn.execute(
                    "UPDATE carteiras SET active = ?, descricao = COALESCE(NULLIF(?, ''), descricao), updated_at = ? WHERE id = ?",
                    (True, str(descricao or "").strip(), now, int(current["id"])),
                )
            else:
                self._insert_returning_id(
                    conn,
                    """
                    INSERT INTO carteiras (nome, descricao, active, created_at, updated_at)
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (carteira, str(descricao or "").strip(), True, now, now),
                )
        return next((item for item in self.list_carteiras() if item["nome"] == carteira), {"nome": carteira})

    def deactivate_carteira(self, nome: str) -> dict[str, Any]:
        carteira = self._normalize_carteira_nome(nome)
        if not carteira:
            raise ValueError("Nome da carteira obrigatorio.")
        now = datetime.now().isoformat(timespec="seconds")
        with self.lock, self.connect() as conn:
            used = conn.execute(
                """
                SELECT 1 FROM negociadores
                WHERE active = 1 AND upper(COALESCE(carteira, '')) = upper(?)
                LIMIT 1
                """,
                (carteira,),
            ).fetchone()
            if used:
                raise ValueError("Carteira possui negociadores vinculados e nao pode ser excluida.")
            current = conn.execute("SELECT id FROM carteiras WHERE upper(nome) = upper(?)", (carteira,)).fetchone()
            if not current:
                raise ValueError("Carteira nao encontrada.")
            conn.execute("UPDATE carteiras SET active = ?, updated_at = ? WHERE id = ?", (False, now, int(current["id"])))
        return {"ok": True, "nome": carteira}

    def _normalize_carteira_nome(self, value: Any) -> str:
        return " ".join(str(value or "").strip().upper().split())

    def list_negociadores(self) -> list[dict[str, Any]]:
        with self.lock, self.connect() as conn:
            rows = conn.execute("SELECT * FROM negociadores WHERE active = 1 ORDER BY nome").fetchall()
            result: list[dict[str, Any]] = []
            seen_system_users: set[str] = set()
            for row in rows:
                negociador = self._decode_negociador(row)
                if str(negociador.get("source_type") or "").strip().lower() == "sistema":
                    username = str(negociador.get("negocial_username") or "").strip().lower()
                    if username:
                        if username in seen_system_users:
                            continue
                        seen_system_users.add(username)
                result.append(negociador)
            return result

    def get_negociador(self, negociador_id: int) -> dict[str, Any] | None:
        with self.lock, self.connect() as conn:
            row = conn.execute("SELECT * FROM negociadores WHERE id = ?", (negociador_id,)).fetchone()
            return self._decode_negociador(row) if row else None

    def find_system_negociador(self, username: str, active_only: bool = False) -> dict[str, Any] | None:
        username = str(username or "").strip()
        if not username:
            return None
        query = """
            SELECT *
            FROM negociadores
            WHERE source_type = ? AND lower(negocial_username) = lower(?)
        """
        params: list[Any] = ["sistema", username]
        if active_only:
            query += " AND active = 1"
        query += " ORDER BY active DESC, id ASC LIMIT 1"
        with self.lock, self.connect() as conn:
            row = conn.execute(query, tuple(params)).fetchone()
            return dict(row) if row else None

    def create_negociador(self, payload: dict[str, Any]) -> int:
        now = datetime.now().isoformat(timespec="seconds")
        with self.lock, self.connect() as conn:
            return self._insert_returning_id(
                conn,
                """
                INSERT INTO negociadores (
                    nome, carteira, arquivo_path, sheet, senha, source_type, negocial_user_id,
                    negocial_username, meta_pagamento, active, last_mtime, created_at, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    payload["nome"],
                    payload.get("carteira"),
                    payload["arquivo_path"],
                    payload["sheet"],
                    self.credentials.encrypt(payload.get("senha")),
                    payload.get("source_type") or "planilha",
                    payload.get("negocial_user_id"),
                    payload.get("negocial_username"),
                    payload.get("meta_pagamento"),
                    True,
                    payload.get("last_mtime"),
                    now,
                    now,
                ),
            )

    def upsert_system_negociador_login(self, payload: dict[str, Any]) -> int:
        now = datetime.now().isoformat(timespec="seconds")
        username = str(payload.get("negocial_username") or "").strip()
        if not username:
            raise ValueError("Usuario negocial obrigatorio.")
        with self.lock, self.connect() as conn:
            current = conn.execute(
                """
                SELECT id
                FROM negociadores
                WHERE source_type = ? AND lower(negocial_username) = lower(?)
                ORDER BY active DESC, id ASC
                LIMIT 1
                """,
                ("sistema", username),
            ).fetchone()
            if current:
                conn.execute(
                    """
                    UPDATE negociadores
                    SET active = ?, updated_at = ?
                    WHERE source_type = ? AND lower(negocial_username) = lower(?) AND id <> ?
                    """,
                    (False, now, "sistema", username, int(current["id"])),
                )
                conn.execute(
                    """
                    UPDATE negociadores
                    SET nome = ?, carteira = ?, arquivo_path = ?, sheet = ?, senha = NULL,
                        source_type = ?, negocial_user_id = ?, negocial_username = ?, meta_pagamento = ?,
                        active = ?, updated_at = ?
                    WHERE id = ?
                    """,
                    (
                        payload["nome"],
                        payload.get("carteira"),
                        payload["arquivo_path"],
                        payload["sheet"],
                        "sistema",
                        payload.get("negocial_user_id"),
                        username,
                        payload.get("meta_pagamento"),
                        True,
                        now,
                        int(current["id"]),
                    ),
                )
                return int(current["id"])
            return self._insert_returning_id(
                conn,
                """
                INSERT INTO negociadores (
                    nome, carteira, arquivo_path, sheet, senha, source_type, negocial_user_id,
                    negocial_username, meta_pagamento, active, last_mtime, created_at, updated_at
                )
                VALUES (?, ?, ?, ?, NULL, ?, ?, ?, ?, ?, NULL, ?, ?)
                """,
                (
                    payload["nome"],
                    payload.get("carteira"),
                    payload["arquivo_path"],
                    payload["sheet"],
                    "sistema",
                    payload.get("negocial_user_id"),
                    username,
                    payload.get("meta_pagamento"),
                    True,
                    now,
                    now,
                ),
            )

    def update_negociador(self, negociador_id: int, payload: dict[str, Any]) -> None:
        now = datetime.now().isoformat(timespec="seconds")
        current = self.get_negociador(negociador_id)
        if not current:
            raise ValueError("Negociador nao encontrado")
        merged = {**current, **payload}
        with self.lock, self.connect() as conn:
            conn.execute(
                """
                UPDATE negociadores
                SET nome = ?, carteira = ?, arquivo_path = ?, sheet = ?, senha = ?, source_type = ?,
                    negocial_user_id = ?, negocial_username = ?, meta_pagamento = ?, last_mtime = ?, updated_at = ?
                WHERE id = ?
                """,
                (
                    merged["nome"],
                    merged.get("carteira"),
                    merged["arquivo_path"],
                    merged["sheet"],
                    self.credentials.encrypt(merged.get("senha")),
                    merged.get("source_type") or "planilha",
                    merged.get("negocial_user_id"),
                    merged.get("negocial_username"),
                    merged.get("meta_pagamento"),
                    merged.get("last_mtime"),
                    now,
                    negociador_id,
                ),
            )

    def soft_delete_negociador(self, negociador_id: int) -> None:
        with self.lock, self.connect() as conn:
            conn.execute("UPDATE negociadores SET active = ?, updated_at = ? WHERE id = ?", (False, datetime.now().isoformat(timespec="seconds"), negociador_id))

    def _decode_negociador(self, row: Any) -> dict[str, Any]:
        negociador = dict(row)
        negociador["senha"] = self.credentials.decrypt(negociador.get("senha"))
        return negociador

    def create_snapshot(self, negociador_id: int, sheet: str, content: dict[str, Any]) -> int:
        with self.lock, self.connect() as conn:
            snapshot_id = self._insert_returning_id(
                conn,
                "INSERT INTO snapshots (negociador_id, sheet, captured_at, content_json) VALUES (?, ?, ?, ?)",
                (negociador_id, sheet, datetime.now().isoformat(timespec="seconds"), self._json_param(content)),
            )
            self._snapshot_content_cache[snapshot_id] = content
            return snapshot_id

    def latest_snapshot(self, negociador_id: int, sheet: str | None = None) -> dict[str, Any] | None:
        query = "SELECT * FROM snapshots WHERE negociador_id = ?"
        params: list[Any] = [negociador_id]
        if sheet:
            query += " AND sheet = ?"
            params.append(sheet)
        query += " ORDER BY id DESC LIMIT 1"
        with self.lock, self.connect() as conn:
            row = conn.execute(query, params).fetchone()
            if not row:
                return None
            result = dict(row)
            result["content"] = self._snapshot_content(result)
            return result

    def latest_snapshot_for_month(self, negociador_id: int, month_key: str, sheet: str | None = None) -> dict[str, Any] | None:
        query = "SELECT * FROM snapshots WHERE negociador_id = ? AND captured_at LIKE ?"
        if self.backend == "postgresql":
            query = "SELECT * FROM snapshots WHERE negociador_id = ? AND captured_at::text LIKE ?"
        params: list[Any] = [negociador_id, f"{month_key}%"]
        if sheet:
            query += " AND sheet = ?"
            params.append(sheet)
        query += " ORDER BY captured_at DESC, id DESC LIMIT 1"
        with self.lock, self.connect() as conn:
            row = conn.execute(query, params).fetchone()
            if not row:
                return None
            result = dict(row)
            result["content"] = self._snapshot_content(result)
            return result

    def _snapshot_content(self, row: dict[str, Any]) -> dict[str, Any]:
        snapshot_id = int(row["id"])
        content_json = row.pop("content_json")
        if snapshot_id not in self._snapshot_content_cache:
            self._snapshot_content_cache[snapshot_id] = self._decode_json(content_json)
        return self._snapshot_content_cache[snapshot_id]

    def create_event(self, payload: dict[str, Any]) -> int:
        with self.lock, self.connect() as conn:
            return self._insert_returning_id(
                conn,
                """
                INSERT INTO events (
                    negociador_id, snapshot_before_id, snapshot_after_id, event_type, sheet, file_path,
                    changed_at, changes_count, delta_json, metadata_json
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    payload["negociador_id"],
                    payload.get("snapshot_before_id"),
                    payload["snapshot_after_id"],
                    payload["event_type"],
                    payload["sheet"],
                    payload["file_path"],
                    payload["changed_at"],
                    payload["changes_count"],
                    self._json_param(payload["delta"]),
                    self._json_param(payload["metadata"]),
                ),
            )

    def list_events(self, negociador_id: int | None = None, limit: int = 200) -> list[dict[str, Any]]:
        params: list[Any] = []
        query = """
            SELECT e.*, n.nome AS negociador_nome, n.carteira AS carteira
            FROM events e
            JOIN negociadores n ON n.id = e.negociador_id
        """
        if negociador_id:
            query += " WHERE e.negociador_id = ?"
            params.append(negociador_id)
        else:
            query += " WHERE n.active = 1"
        query += " ORDER BY e.id DESC LIMIT ?"
        params.append(limit)
        with self.lock, self.connect() as conn:
            rows = conn.execute(query, params).fetchall()
            return [self._decode_event(dict(row)) for row in rows]

    def get_event(self, event_id: int) -> dict[str, Any] | None:
        with self.lock, self.connect() as conn:
            row = conn.execute(
                """
                SELECT e.*, n.nome AS negociador_nome
                FROM events e
                JOIN negociadores n ON n.id = e.negociador_id
                WHERE e.id = ?
                """,
                (event_id,),
            ).fetchone()
            return self._decode_event(dict(row)) if row else None

    def list_overview_events(self, usuario: str, limit: int = 300) -> list[dict[str, Any]]:
        with self.lock, self.connect() as conn:
            rows = conn.execute(
                """
                SELECT e.*, n.nome AS negociador_nome, n.carteira AS carteira
                FROM events e
                JOIN negociadores n ON n.id = e.negociador_id
                WHERE e.event_type <> 'initial_snapshot' AND n.active = 1
                ORDER BY e.id DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
            if rows:
                event_ids = [int(row["id"]) for row in rows]
                read_rows = conn.execute(
                    """
                    SELECT event_id, change_index
                    FROM overview_reads
                    WHERE usuario = ? AND event_id BETWEEN ? AND ?
                    """,
                    (usuario, min(event_ids), max(event_ids)),
                ).fetchall()
            else:
                read_rows = []
            read_keys = {(row["event_id"], row["change_index"]) for row in read_rows}
            events = []
            for row in rows:
                event = self._decode_event(dict(row))
                event["read_keys"] = read_keys
                events.append(event)
            return events

    def list_unread_overview_events(self, usuario: str, limit: int = 300) -> list[dict[str, Any]]:
        return self.list_overview_events(usuario, limit)

    def mark_overview_read(self, event_id: int, change_index: int, usuario: str) -> None:
        self.mark_overview_reads([(event_id, change_index)], usuario)

    def mark_overview_reads(self, entries: list[tuple[int, int]], usuario: str) -> int:
        unique_entries = sorted({(int(event_id), int(change_index)) for event_id, change_index in entries})
        if not unique_entries:
            return 0
        now = datetime.now().isoformat(timespec="seconds")
        with self.lock, self.connect() as conn:
            for event_id, change_index in unique_entries:
                conn.execute(
                    """
                    INSERT OR IGNORE INTO overview_reads (event_id, change_index, usuario, read_at)
                    VALUES (?, ?, ?, ?)
                    """,
                    (event_id, change_index, usuario, now),
                )
        return len(unique_entries)

    def list_notification_reads(self, usuario: str) -> set[str]:
        with self.lock, self.connect() as conn:
            rows = conn.execute(
                "SELECT notification_id FROM notification_reads WHERE usuario = ?",
                (usuario,),
            ).fetchall()
            return {str(row["notification_id"]) for row in rows}

    def mark_notification_read(self, notification_id: str, usuario: str) -> None:
        with self.lock, self.connect() as conn:
            conn.execute(
                """
                INSERT OR IGNORE INTO notification_reads (notification_id, usuario, read_at)
                VALUES (?, ?, ?)
                """,
                (notification_id, usuario, datetime.now().isoformat(timespec="seconds")),
            )

    def list_notes(self, target_type: str, target_id: str) -> list[dict[str, Any]]:
        with self.lock, self.connect() as conn:
            rows = conn.execute(
                """
                SELECT *
                FROM notes
                WHERE target_type = ? AND target_id = ?
                ORDER BY updated_at DESC, id DESC
                """,
                (target_type, target_id),
            ).fetchall()
            return [dict(row) for row in rows]

    def create_note(self, target_type: str, target_id: str, text: str, usuario: str) -> dict[str, Any]:
        now = datetime.now().isoformat(timespec="seconds")
        with self.lock, self.connect() as conn:
            note_id = self._insert_returning_id(
                conn,
                """
                INSERT INTO notes (target_type, target_id, text, usuario, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (target_type, target_id, text, usuario, now, now),
            )
            row = conn.execute("SELECT * FROM notes WHERE id = ?", (note_id,)).fetchone()
            return dict(row)

    def update_note(self, note_id: int, text: str, usuario: str) -> dict[str, Any]:
        now = datetime.now().isoformat(timespec="seconds")
        with self.lock, self.connect() as conn:
            row = conn.execute("SELECT * FROM notes WHERE id = ?", (note_id,)).fetchone()
            if not row:
                raise ValueError("Observacao nao encontrada")
            conn.execute(
                "UPDATE notes SET text = ?, usuario = ?, updated_at = ? WHERE id = ?",
                (text, usuario, now, note_id),
            )
            updated = conn.execute("SELECT * FROM notes WHERE id = ?", (note_id,)).fetchone()
            return dict(updated)

    def list_protocolos(self, pending_only: bool = False, limit: int | None = None) -> list[dict[str, Any]]:
        sql = "SELECT * FROM protocolos"
        params: list[Any] = []
        if pending_only:
            sql += " WHERE status <> ?"
            params.append("CONCLUIDO")
        sql += " ORDER BY row_key"
        if limit:
            sql += " LIMIT ?"
            params.append(max(0, int(limit)))
        with self.lock, self.connect() as conn:
            rows = conn.execute(sql, tuple(params)).fetchall()
            return [self._decode_protocolo(dict(row)) for row in rows]

    def upsert_protocolos(self, records: list[dict[str, Any]], usuario: str = "migracao") -> int:
        now = datetime.now().isoformat(timespec="seconds")
        count = 0
        with self.lock, self.connect() as conn:
            for record in records:
                row_key = int(record.get("row_key") or 0)
                if row_key <= 0:
                    continue
                extra = record.get("extra") or {}
                conn.execute(
                    """
                    INSERT INTO protocolos (
                        row_key, data_mes, carteira, nome, pj, processo, data_solicitacao,
                        status, data_conclusao, observacao, extra_json, source,
                        created_by, updated_by, created_at, updated_at
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(row_key) DO UPDATE SET
                        data_mes = excluded.data_mes,
                        carteira = excluded.carteira,
                        nome = excluded.nome,
                        pj = excluded.pj,
                        processo = excluded.processo,
                        data_solicitacao = excluded.data_solicitacao,
                        status = excluded.status,
                        data_conclusao = excluded.data_conclusao,
                        observacao = excluded.observacao,
                        extra_json = excluded.extra_json,
                        source = excluded.source,
                        updated_by = excluded.updated_by,
                        updated_at = excluded.updated_at
                    """,
                    (
                        row_key,
                        record.get("data_mes", ""),
                        record.get("carteira", ""),
                        record.get("nome", ""),
                        record.get("pj", ""),
                        record.get("processo", ""),
                        record.get("data_solicitacao", ""),
                        record.get("status", "PENDENTE"),
                        record.get("data_conclusao", ""),
                        record.get("observacao", ""),
                        self._json_param(extra),
                        record.get("source", "excel_import"),
                        usuario,
                        usuario,
                        now,
                        now,
                    ),
                )
                count += 1
        return count

    def create_protocolo(self, record: dict[str, Any], usuario: str) -> dict[str, Any]:
        now = datetime.now().isoformat(timespec="seconds")
        with self.lock, self.connect() as conn:
            next_row = conn.execute("SELECT COALESCE(MAX(row_key), 0) + 1 AS row_key FROM protocolos").fetchone()
            row_key = int(next_row["row_key"] if isinstance(next_row, dict) else next_row[0])
            protocolo_id = self._insert_returning_id(
                conn,
                """
                INSERT INTO protocolos (
                    row_key, data_mes, carteira, nome, pj, processo, data_solicitacao,
                    status, data_conclusao, observacao, extra_json, source,
                    created_by, updated_by, created_at, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    row_key,
                    record.get("data_mes", ""),
                    record.get("carteira", ""),
                    record.get("nome", ""),
                    record.get("pj", ""),
                    record.get("processo", ""),
                    record.get("data_solicitacao", ""),
                    record.get("status", "PENDENTE"),
                    record.get("data_conclusao", ""),
                    record.get("observacao", ""),
                    self._json_param(record.get("extra") or {}),
                    "database",
                    usuario,
                    usuario,
                    now,
                    now,
                ),
            )
            row = conn.execute("SELECT * FROM protocolos WHERE id = ?", (protocolo_id,)).fetchone()
            return self._decode_protocolo(dict(row))

    def update_protocolo_status(self, row_key: int, status: str, data_conclusao: str, usuario: str) -> dict[str, Any]:
        now = datetime.now().isoformat(timespec="seconds")
        with self.lock, self.connect() as conn:
            row = conn.execute("SELECT id FROM protocolos WHERE row_key = ?", (row_key,)).fetchone()
            if not row:
                raise ValueError("Protocolo nao encontrado.")
            conn.execute(
                """
                UPDATE protocolos
                SET status = ?, data_conclusao = ?, updated_by = ?, updated_at = ?
                WHERE row_key = ?
                """,
                (status, data_conclusao, usuario, now, row_key),
            )
            updated = conn.execute("SELECT * FROM protocolos WHERE row_key = ?", (row_key,)).fetchone()
            return self._decode_protocolo(dict(updated))

    def update_protocolo_field(self, row_key: int, field: str, value: Any, usuario: str) -> dict[str, Any]:
        columns = {
            "data_mes",
            "carteira",
            "nome",
            "pj",
            "processo",
            "data_solicitacao",
            "data_conclusao",
            "observacao",
        }
        field = str(field or "").strip()
        if field not in columns:
            raise ValueError("Campo de protocolo invalido.")
        now = datetime.now().isoformat(timespec="seconds")
        with self.lock, self.connect() as conn:
            row = conn.execute("SELECT id FROM protocolos WHERE row_key = ?", (row_key,)).fetchone()
            if not row:
                raise ValueError("Protocolo nao encontrado.")
            conn.execute(
                f"UPDATE protocolos SET {field} = ?, updated_by = ?, updated_at = ? WHERE row_key = ?",
                ("" if value is None else value, usuario, now, row_key),
            )
            updated = conn.execute("SELECT * FROM protocolos WHERE row_key = ?", (row_key,)).fetchone()
            return self._decode_protocolo(dict(updated))

    def replace_colchao_records(self, profile: str, records: list[dict[str, Any]], usuario: str = "sync") -> int:
        carteira = self._colchao_profile(profile)
        now = datetime.now().isoformat(timespec="seconds")
        with self.lock, self.connect() as conn:
            conn.execute(
                "UPDATE colchao_parcelas SET active = 0, updated_by = ?, updated_at = ? WHERE carteira = ?",
                (usuario, now, carteira),
            )
            conn.execute(
                "UPDATE colchao_acordos SET active = 0, updated_by = ?, updated_at = ? WHERE carteira = ?",
                (usuario, now, carteira),
            )
            count = 0
            for record in records:
                if self._upsert_colchao_record_conn(conn, carteira, record, usuario, now) is None:
                    continue
                count += 1
        return count

    def get_colchao_config(self, profile: str) -> dict[str, Any] | None:
        carteira = self._colchao_profile(profile)
        with self.lock, self.connect() as conn:
            row = conn.execute(
                "SELECT version, config_json, updated_by, updated_at FROM colchao_configuracoes WHERE carteira = ?",
                (carteira,),
            ).fetchone()
        if not row:
            return None
        row = dict(row)
        payload = self._decode_json(row["config_json"])
        payload["version"] = int(row["version"] or 1)
        payload["updated_by"] = row.get("updated_by")
        payload["updated_at"] = row.get("updated_at")
        return payload

    def save_colchao_config(self, profile: str, config: dict[str, Any], usuario: str) -> dict[str, Any]:
        carteira = self._colchao_profile(profile)
        now = datetime.now().isoformat(timespec="seconds")
        with self.lock, self.connect() as conn:
            current = conn.execute(
                "SELECT version FROM colchao_configuracoes WHERE carteira = ?",
                (carteira,),
            ).fetchone()
            version = int(current["version"] or 0) + 1 if current else 1
            stored = dict(config)
            stored.pop("version", None)
            stored.pop("updated_by", None)
            stored.pop("updated_at", None)
            encoded = self._json_param(stored)
            conn.execute(
                """
                INSERT INTO colchao_configuracoes (
                    carteira, version, config_json, updated_by, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(carteira) DO UPDATE SET
                    version = excluded.version,
                    config_json = excluded.config_json,
                    updated_by = excluded.updated_by,
                    updated_at = excluded.updated_at
                """,
                (carteira, version, encoded, usuario, now, now),
            )
            conn.execute(
                """
                INSERT INTO colchao_configuracao_versions (
                    carteira, version, config_json, created_by, created_at
                ) VALUES (?, ?, ?, ?, ?)
                """,
                (carteira, version, encoded, usuario, now),
            )
        return {**stored, "version": version, "updated_by": usuario, "updated_at": now}

    def list_colchao_config_versions(self, profile: str, limit: int = 30) -> list[dict[str, Any]]:
        carteira = self._colchao_profile(profile)
        with self.lock, self.connect() as conn:
            rows = conn.execute(
                """
                SELECT version, config_json, created_by, created_at
                FROM colchao_configuracao_versions
                WHERE carteira = ?
                ORDER BY version DESC
                LIMIT ?
                """,
                (carteira, max(1, min(int(limit), 100))),
            ).fetchall()
        return [
            {
                "version": int(row["version"]),
                "config": self._decode_json(row["config_json"]),
                "created_by": row["created_by"],
                "created_at": row["created_at"],
            }
            for row in rows
        ]

    def append_colchao_records(self, profile: str, records: list[dict[str, Any]], usuario: str) -> list[int]:
        carteira = self._colchao_profile(profile)
        now = datetime.now().isoformat(timespec="seconds")
        created_rows: list[int] = []
        with self.lock, self.connect() as conn:
            next_by_sheet: dict[str, int] = {}
            for record in records:
                sheet_name = str(record.get("__sheet_name") or "COLCHAO").strip() or "COLCHAO"
                if sheet_name not in next_by_sheet:
                    row = conn.execute(
                        "SELECT COALESCE(MAX(source_row), 1) AS last_row FROM colchao_parcelas WHERE carteira = ? AND source_sheet = ?",
                        (carteira, sheet_name),
                    ).fetchone()
                    next_by_sheet[sheet_name] = int(row["last_row"] or 1) + 1
                payload = dict(record)
                payload["__sheet_name"] = sheet_name
                payload["__row_number"] = next_by_sheet[sheet_name]
                next_by_sheet[sheet_name] += 1
                row_number = self._upsert_colchao_record_conn(conn, carteira, payload, usuario, now, source="database")
                if row_number is not None:
                    created_rows.append(row_number)
        return created_rows

    def _upsert_colchao_record_conn(
        self,
        conn: DatabaseConnection,
        carteira: str,
        record: dict[str, Any],
        usuario: str,
        now: str,
        source: str = "excel_sync",
    ) -> int | None:
        row_number = int(record.get("__row_number") or 0)
        sheet_name = str(record.get("__sheet_name") or "COLCHAO").strip() or "COLCHAO"
        if row_number <= 0:
            return None
        identifier = str(record.get("__identifier") or f"__ROW__{row_number}").strip()
        agreement_number = str(record.get("__acordo") or "1").strip() or "1"
        conn.execute(
            """
            INSERT INTO colchao_acordos (
                carteira, source_sheet, identifier, agreement_number, cliente, cpf_cnpj,
                operador, tipo_acordo, metadata_json, active, source, created_by,
                updated_by, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(carteira, source_sheet, identifier, agreement_number) DO UPDATE SET
                cliente = excluded.cliente,
                cpf_cnpj = excluded.cpf_cnpj,
                operador = excluded.operador,
                tipo_acordo = excluded.tipo_acordo,
                active = excluded.active,
                source = excluded.source,
                updated_by = excluded.updated_by,
                updated_at = excluded.updated_at
            """,
            (
                carteira, sheet_name, identifier, agreement_number,
                record.get("__cliente", ""), record.get("__cpf_cnpj", ""),
                record.get("__operador", ""), record.get("__tipo_acordo", ""),
                self._json_param({}), True, source, usuario, usuario, now, now,
            ),
        )
        agreement = conn.execute(
            """SELECT id FROM colchao_acordos
               WHERE carteira = ? AND source_sheet = ? AND identifier = ? AND agreement_number = ?""",
            (carteira, sheet_name, identifier, agreement_number),
        ).fetchone()
        conn.execute(
            """
            INSERT INTO colchao_parcelas (
                acordo_id, carteira, source_sheet, source_row, parcela, valor, vencimento,
                status, observacao, bucket, raw_json, active, source_updated_at,
                updated_by, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(carteira, source_sheet, source_row) DO UPDATE SET
                acordo_id = excluded.acordo_id,
                parcela = excluded.parcela,
                valor = excluded.valor,
                vencimento = excluded.vencimento,
                status = excluded.status,
                observacao = excluded.observacao,
                bucket = excluded.bucket,
                raw_json = excluded.raw_json,
                active = excluded.active,
                source_updated_at = excluded.source_updated_at,
                updated_by = excluded.updated_by,
                updated_at = excluded.updated_at
            """,
            (
                int(agreement["id"]), carteira, sheet_name, row_number,
                record.get("__parcela", ""), record.get("__valor", 0),
                record.get("__vencimento", ""), record.get("__status", "A VENCER"),
                record.get("__observacao", ""), record.get("__bucket", ""),
                self._json_param(record.get("__raw") or {}), True, now,
                usuario, now, now,
            ),
        )
        return row_number

    def list_colchao_records(self, profile: str, sheet_name: str = "") -> list[dict[str, Any]]:
        carteira = self._colchao_profile(profile)
        sql = """
            SELECT p.id, p.source_sheet AS sheet_name, p.source_row AS row_number,
                   a.identifier, a.cliente, a.cpf_cnpj, a.agreement_number AS acordo,
                   p.parcela, p.valor, p.vencimento, p.status, p.observacao,
                   a.operador, p.bucket, p.raw_json, p.active, p.source_updated_at,
                   p.updated_by, p.created_at, p.updated_at, a.carteira AS profile
            FROM colchao_parcelas p
            JOIN colchao_acordos a ON a.id = p.acordo_id
            WHERE p.active = 1 AND a.active = 1 AND p.carteira = ?
        """
        params: list[Any] = [carteira]
        if sheet_name:
            sql += " AND p.source_sheet = ?"
            params.append(sheet_name)
        sql += " ORDER BY p.source_sheet, p.source_row"
        with self.lock, self.connect() as conn:
            rows = conn.execute(sql, tuple(params)).fetchall()
            return [self._decode_colchao_record(dict(row)) for row in rows]

    def update_colchao_status(
        self,
        profile: str,
        sheet_name: str,
        row_number: int,
        status: str,
        observacao: str,
        bucket: str,
        usuario: str,
    ) -> None:
        carteira = self._colchao_profile(profile)
        now = datetime.now().isoformat(timespec="seconds")
        with self.lock, self.connect() as conn:
            row = conn.execute(
                "SELECT raw_json FROM colchao_parcelas WHERE carteira = ? AND source_sheet = ? AND source_row = ? AND active = 1",
                (carteira, sheet_name, int(row_number)),
            ).fetchone()
            if not row:
                raise ValueError("Registro do colchao nao encontrado.")
            raw = self._decode_json(row["raw_json"])
            raw["STATUS"] = status
            if observacao:
                raw["OBS"] = observacao
                raw["OBSERVACOES"] = observacao
                raw["OBSERVAÃ‡Ã•ES"] = observacao
            conn.execute(
                f"""
                UPDATE colchao_parcelas
                SET status = ?, observacao = ?, bucket = ?, raw_json = ?, updated_by = ?, updated_at = ?
                WHERE carteira = ? AND source_sheet = ? AND source_row = ? AND active = 1
                """,
                (
                    status,
                    observacao,
                    bucket,
                    self._json_param(raw),
                    usuario,
                    now,
                    carteira,
                    sheet_name,
                    int(row_number),
                ),
            )

    def update_colchao_due_date(
        self,
        profile: str,
        sheet_name: str,
        row_number: int,
        due_date: str,
        header: str,
        bucket: str,
        usuario: str,
    ) -> None:
        carteira = self._colchao_profile(profile)
        now = datetime.now().isoformat(timespec="seconds")
        with self.lock, self.connect() as conn:
            row = conn.execute(
                "SELECT raw_json FROM colchao_parcelas WHERE carteira = ? AND source_sheet = ? AND source_row = ? AND active = 1",
                (carteira, sheet_name, int(row_number)),
            ).fetchone()
            if not row:
                raise ValueError("Registro do colchao nao encontrado.")
            raw = self._decode_json(row["raw_json"])
            raw[str(header or "DATA DO VENCIMENTO")] = due_date
            conn.execute(
                """
                UPDATE colchao_parcelas
                SET vencimento = ?, bucket = ?, raw_json = ?, updated_by = ?, updated_at = ?
                WHERE carteira = ? AND source_sheet = ? AND source_row = ? AND active = 1
                """,
                (
                    due_date,
                    bucket,
                    self._json_param(raw),
                    usuario,
                    now,
                    carteira,
                    sheet_name,
                    int(row_number),
                ),
            )

    def update_colchao_due_dates_batch(
        self,
        profile: str,
        changes: list[dict[str, Any]],
        usuario: str,
    ) -> int:
        carteira = self._colchao_profile(profile)
        now = datetime.now().isoformat(timespec="seconds")
        updated = 0
        with self.lock, self.connect() as conn:
            for change in changes:
                sheet_name = str(change.get("sheet") or "").strip()
                row_number = int(change.get("row") or 0)
                if not sheet_name or row_number <= 0:
                    raise ValueError("Parcela do colchao invalida para reprogramacao.")
                row = conn.execute(
                    """
                    SELECT raw_json, status
                    FROM colchao_parcelas
                    WHERE carteira = ? AND source_sheet = ? AND source_row = ? AND active = 1
                    """,
                    (carteira, sheet_name, row_number),
                ).fetchone()
                if not row:
                    raise ValueError(f"Parcela {sheet_name} linha {row_number} nao encontrada.")
                if str(row["status"] or "").strip().upper() not in {"A VENCER", "VENCIDO"}:
                    raise ValueError("Parcelas pagas ou quebradas nao podem ser reprogramadas.")
                raw = self._decode_json(row["raw_json"])
                raw[str(change.get("header") or "DATA DO VENCIMENTO")] = str(change.get("depois") or "")
                conn.execute(
                    """
                    UPDATE colchao_parcelas
                    SET vencimento = ?, bucket = ?, raw_json = ?, updated_by = ?, updated_at = ?
                    WHERE carteira = ? AND source_sheet = ? AND source_row = ? AND active = 1
                    """,
                    (
                        str(change.get("depois") or ""),
                        str(change.get("bucket") or ""),
                        self._json_param(raw),
                        usuario,
                        now,
                        carteira,
                        sheet_name,
                        row_number,
                    ),
                )
                updated += 1
        return updated

    def _decode_protocolo(self, row: dict[str, Any]) -> dict[str, Any]:
        row["extra"] = self._decode_json(row.get("extra_json") or {})
        row.pop("extra_json", None)
        return row

    def _colchao_profile(self, profile: str) -> str:
        value = str(profile or "").strip().upper()
        if not value or not all(char.isalnum() or char in {"_", "-"} for char in value):
            raise ValueError("Carteira do colchao invalida.")
        return value

    def _decode_colchao_record(self, row: dict[str, Any]) -> dict[str, Any]:
        raw = self._decode_json(row.get("raw_json") or {})
        raw["__db_id"] = row.get("id")
        raw["__row_number"] = row.get("row_number")
        raw["__sheet_name"] = row.get("sheet_name")
        raw["__bucket"] = row.get("bucket")
        raw["__profile"] = str(row.get("profile") or "")
        return raw

    def ensure_user(self, username: str, password: str, role: str = "user") -> None:
        with self.lock, self.connect() as conn:
            self._ensure_user_conn(conn, username, password, role)

    def list_users(self) -> list[dict[str, Any]]:
        with self.lock, self.connect() as conn:
            rows = conn.execute(
                """
                SELECT
                    u.id,
                    u.username,
                    u.role,
                    u.active,
                    u.created_at,
                    u.updated_at,
                    SUM(CASE WHEN s.expires_at > ? THEN 1 ELSE 0 END) AS online_sessions,
                    MAX(s.created_at) AS last_access_at
                FROM users u
                LEFT JOIN sessions s ON s.user_id = u.id
                GROUP BY u.id, u.username, u.role, u.active, u.created_at, u.updated_at
                ORDER BY u.username
                """
                if self.backend == "sqlite"
                else """
                SELECT
                    u.id,
                    u.username,
                    u.role,
                    u.active,
                    u.created_at,
                    u.updated_at,
                    COUNT(s.token) FILTER (WHERE s.expires_at > NOW()) AS online_sessions,
                    MAX(s.created_at) AS last_access_at
                FROM users u
                LEFT JOIN sessions s ON s.user_id = u.id
                GROUP BY u.id, u.username, u.role, u.active, u.created_at, u.updated_at
                ORDER BY u.username
                """,
                (datetime.now().isoformat(timespec="seconds"),) if self.backend == "sqlite" else (),
            ).fetchall()
            users = []
            for row in rows:
                user = dict(row)
                user["online"] = int(user.get("online_sessions") or 0) > 0
                users.append(user)
            return users

    def create_user(self, username: str, password: str, role: str = "user") -> dict[str, Any]:
        username = " ".join(str(username or "").strip().split())
        password = str(password or "")
        role = str(role or "user").strip().lower()
        if not username:
            raise ValueError("Usuario obrigatorio.")
        if not password:
            raise ValueError("Senha obrigatoria.")
        allowed_roles = {"superadmin", "admin", "gerencial", "supervisor", "user", "negociador"}
        if role not in allowed_roles:
            raise ValueError("Perfil invalido.")
        if role == "negociador":
            role = "user"
        now = datetime.now().isoformat(timespec="seconds")
        salt = secrets.token_hex(16)
        with self.lock, self.connect() as conn:
            current = conn.execute("SELECT id FROM users WHERE username = ?", (username,)).fetchone()
            if current:
                raise ValueError("Ja existe um usuario com este login.")
            user_id = self._insert_returning_id(
                conn,
                """
                INSERT INTO users (username, password_hash, salt, role, active, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (username, self._hash_password(password, salt), salt, role, True, now, now),
            )
            row = conn.execute(
                "SELECT id, username, role, active, created_at, updated_at FROM users WHERE id = ?",
                (user_id,),
            ).fetchone()
            return dict(row)

    def get_user(self, user_id: int) -> dict[str, Any] | None:
        with self.lock, self.connect() as conn:
            row = conn.execute(
                "SELECT id, username, role, active, created_at, updated_at FROM users WHERE id = ?",
                (int(user_id),),
            ).fetchone()
            return dict(row) if row else None

    def update_user(self, user_id: int, username: str, role: str, password: str = "") -> dict[str, Any]:
        username = " ".join(str(username or "").strip().split())
        role = str(role or "").strip().lower()
        password = str(password or "")
        if not username:
            raise ValueError("Usuario obrigatorio.")
        if role not in {"superadmin", "admin", "gerencial", "supervisor", "user"}:
            raise ValueError("Perfil invalido.")
        now = datetime.now().isoformat(timespec="seconds")
        with self.lock, self.connect() as conn:
            current = conn.execute("SELECT id FROM users WHERE id = ?", (int(user_id),)).fetchone()
            if not current:
                raise ValueError("Usuario nao encontrado.")
            duplicate = conn.execute(
                "SELECT id FROM users WHERE lower(username) = lower(?) AND id <> ?",
                (username, int(user_id)),
            ).fetchone()
            if duplicate:
                raise ValueError("Ja existe um usuario com este login.")
            if password:
                salt = secrets.token_hex(16)
                conn.execute(
                    "UPDATE users SET username = ?, role = ?, password_hash = ?, salt = ?, updated_at = ? WHERE id = ?",
                    (username, role, self._hash_password(password, salt), salt, now, int(user_id)),
                )
            else:
                conn.execute(
                    "UPDATE users SET username = ?, role = ?, updated_at = ? WHERE id = ?",
                    (username, role, now, int(user_id)),
                )
            conn.execute("DELETE FROM sessions WHERE user_id = ?", (int(user_id),))
            updated = conn.execute(
                "SELECT id, username, role, active, created_at, updated_at FROM users WHERE id = ?",
                (int(user_id),),
            ).fetchone()
            return dict(updated)

    def active_superadmin_count(self) -> int:
        with self.lock, self.connect() as conn:
            row = conn.execute(
                "SELECT COUNT(*) AS total FROM users WHERE lower(role) = 'superadmin' AND active = 1"
            ).fetchone()
            return int(row["total"] or 0)

    def set_user_active(self, user_id: int, active: bool) -> dict[str, Any]:
        now = datetime.now().isoformat(timespec="seconds")
        with self.lock, self.connect() as conn:
            row = conn.execute("SELECT id FROM users WHERE id = ?", (user_id,)).fetchone()
            if not row:
                raise ValueError("Usuario nao encontrado.")
            conn.execute("UPDATE users SET active = ?, updated_at = ? WHERE id = ?", (bool(active), now, user_id))
            if not active:
                conn.execute("DELETE FROM sessions WHERE user_id = ?", (user_id,))
            updated = conn.execute(
                "SELECT id, username, role, active, created_at, updated_at FROM users WHERE id = ?",
                (user_id,),
            ).fetchone()
            return dict(updated)

    def delete_user_login(self, user_id: int) -> None:
        with self.lock, self.connect() as conn:
            row = conn.execute("SELECT id FROM users WHERE id = ?", (user_id,)).fetchone()
            if not row:
                raise ValueError("Usuario nao encontrado.")
            conn.execute("DELETE FROM sessions WHERE user_id = ?", (user_id,))
            conn.execute("DELETE FROM users WHERE id = ?", (user_id,))

    def list_role_permissions(self) -> dict[str, Any]:
        with self.lock, self.connect() as conn:
            self._ensure_role_permissions(conn)
            rows = conn.execute(
                "SELECT role, permission, allowed, updated_at FROM role_permissions ORDER BY role, permission"
            ).fetchall()
        roles = {role: dict(DEFAULT_ROLE_PERMISSIONS.get(role, {})) for role in DEFAULT_ROLE_PERMISSIONS}
        for row in rows:
            role = str(row["role"] or "").lower()
            permission = str(row["permission"] or "")
            if role not in roles or permission not in PERMISSION_LABELS:
                continue
            roles[role][permission] = bool(row["allowed"])
        roles["admin"] = {permission: True for permission in PERMISSION_LABELS}
        roles["superadmin"] = {permission: True for permission in PERMISSION_LABELS}
        return {"permissions": PERMISSION_LABELS, "roles": roles}

    def save_role_permissions(self, payload: dict[str, Any]) -> dict[str, Any]:
        roles_payload = payload.get("roles") if isinstance(payload.get("roles"), dict) else {}
        now = datetime.now().isoformat(timespec="seconds")
        with self.lock, self.connect() as conn:
            self._ensure_role_permissions(conn)
            for role in ("gerencial", "supervisor"):
                permissions = roles_payload.get(role) if isinstance(roles_payload.get(role), dict) else {}
                for permission in PERMISSION_LABELS:
                    allowed = bool(permissions.get(permission))
                    current = conn.execute(
                        "SELECT id FROM role_permissions WHERE role = ? AND permission = ?",
                        (role, permission),
                    ).fetchone()
                    if current:
                        conn.execute(
                            "UPDATE role_permissions SET allowed = ?, updated_at = ? WHERE role = ? AND permission = ?",
                            (allowed, now, role, permission),
                        )
                    else:
                        conn.execute(
                            "INSERT INTO role_permissions (role, permission, allowed, updated_at) VALUES (?, ?, ?, ?)",
                            (role, permission, allowed, now),
                        )
            for permission in PERMISSION_LABELS:
                current = conn.execute(
                    "SELECT id FROM role_permissions WHERE role = ? AND permission = ?",
                    ("admin", permission),
                ).fetchone()
                if current:
                    conn.execute(
                        "UPDATE role_permissions SET allowed = ?, updated_at = ? WHERE role = ? AND permission = ?",
                        (True, now, "admin", permission),
                    )
        return self.list_role_permissions()

    def list_user_permission_overrides(self) -> dict[str, Any]:
        with self.lock, self.connect() as conn:
            rows = conn.execute(
                """
                SELECT u.id AS user_id, u.username, u.role, p.permission, p.allowed
                FROM users u
                LEFT JOIN user_permissions p ON p.user_id = u.id
                WHERE u.active = 1
                ORDER BY u.username, p.permission
                """
            ).fetchall()
        users: dict[str, dict[str, Any]] = {}
        for row in rows:
            user_id = str(row["user_id"])
            item = users.setdefault(user_id, {
                "id": int(row["user_id"]),
                "username": row["username"],
                "role": row["role"],
                "overrides": {},
                "effective": self.permissions_for_role(str(row["role"] or "")),
            })
            permission = row["permission"]
            if permission in PERMISSION_LABELS:
                item["overrides"][permission] = bool(row["allowed"])
                item["effective"][permission] = bool(row["allowed"])
        return {"permissions": PERMISSION_LABELS, "users": list(users.values())}

    def save_user_permission_overrides(self, user_id: int, overrides: dict[str, Any]) -> dict[str, Any]:
        now = datetime.now().isoformat(timespec="seconds")
        with self.lock, self.connect() as conn:
            user = conn.execute("SELECT id, username, role FROM users WHERE id = ?", (user_id,)).fetchone()
            if not user:
                raise ValueError("Usuario nao encontrado.")
            conn.execute("DELETE FROM user_permissions WHERE user_id = ?", (user_id,))
            for permission, allowed in (overrides or {}).items():
                if permission not in PERMISSION_LABELS:
                    continue
                if allowed is None:
                    continue
                conn.execute(
                    """
                    INSERT INTO user_permissions (user_id, permission, allowed, updated_at)
                    VALUES (?, ?, ?, ?)
                    """,
                    (user_id, permission, bool(allowed), now),
                )
        return self.user_permission_payload(user_id)

    def user_permission_payload(self, user_id: int) -> dict[str, Any]:
        payload = self.list_user_permission_overrides()
        user = next((item for item in payload["users"] if int(item["id"]) == int(user_id)), None)
        if not user:
            raise ValueError("Usuario nao encontrado.")
        return {"permissions": payload["permissions"], "user": user}

    def has_permission(self, role: str, permission: str, user_id: int | None = None) -> bool:
        role = str(role or "").lower()
        permission = str(permission or "")
        if role in {"admin", "superadmin"}:
            return True
        if permission not in PERMISSION_LABELS:
            return False
        with self.lock, self.connect() as conn:
            if user_id:
                override = conn.execute(
                    "SELECT allowed FROM user_permissions WHERE user_id = ? AND permission = ?",
                    (int(user_id), permission),
                ).fetchone()
                if override is not None:
                    return bool(override["allowed"])
            self._ensure_role_permissions(conn)
            row = conn.execute(
                "SELECT allowed FROM role_permissions WHERE role = ? AND permission = ?",
                (role, permission),
            ).fetchone()
            if row is not None:
                return bool(row["allowed"])
        return bool(DEFAULT_ROLE_PERMISSIONS.get(role, {}).get(permission, False))

    def permissions_for_role(self, role: str, user_id: int | None = None) -> dict[str, bool]:
        role = str(role or "").lower()
        if role in {"admin", "superadmin"}:
            return {permission: True for permission in PERMISSION_LABELS}
        payload = self.list_role_permissions()
        result = dict(payload.get("roles", {}).get(role, DEFAULT_ROLE_PERMISSIONS.get(role, {})))
        if user_id:
            with self.lock, self.connect() as conn:
                rows = conn.execute(
                    "SELECT permission, allowed FROM user_permissions WHERE user_id = ?",
                    (int(user_id),),
                ).fetchall()
            for row in rows:
                if row["permission"] in PERMISSION_LABELS:
                    result[row["permission"]] = bool(row["allowed"])
        return result

    def create_general_audit(self, payload: dict[str, Any]) -> dict[str, Any]:
        now = datetime.now().isoformat(timespec="seconds")
        details = payload.get("details") if isinstance(payload.get("details"), dict) else {}
        with self.lock, self.connect() as conn:
            audit_id = self._insert_returning_id(
                conn,
                """
                INSERT INTO general_audit (
                    actor, actor_role, action, entity_type, entity_id, entity_label,
                    outcome, details_json, ip_address, created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    str(payload.get("actor") or ""),
                    str(payload.get("actor_role") or ""),
                    str(payload.get("action") or "unknown"),
                    str(payload.get("entity_type") or "system"),
                    str(payload.get("entity_id") or ""),
                    str(payload.get("entity_label") or ""),
                    str(payload.get("outcome") or "success"),
                    self._json_param(details),
                    str(payload.get("ip_address") or ""),
                    now,
                ),
            )
            row = conn.execute("SELECT * FROM general_audit WHERE id = ?", (audit_id,)).fetchone()
            return self._decode_general_audit(dict(row))

    def list_general_audit(self, limit: int = 500, filters: dict[str, Any] | None = None) -> list[dict[str, Any]]:
        filters = filters or {}
        limit = max(50, min(int(limit or 500), 2000))
        conditions: list[str] = []
        params: list[Any] = []
        for column, key in (("actor", "actor"), ("action", "action"), ("entity_type", "entity_type"), ("outcome", "outcome")):
            value = str(filters.get(key) or "").strip()
            if not value:
                continue
            conditions.append(f"lower({column}) = lower(?)")
            params.append(value)
        date_from = str(filters.get("date_from") or "").strip()
        if date_from:
            conditions.append("created_at >= ?")
            params.append(date_from)
        date_to = str(filters.get("date_to") or "").strip()
        if date_to:
            conditions.append("created_at <= ?")
            params.append(f"{date_to} 23:59:59" if len(date_to) <= 10 else date_to)
        search = str(filters.get("q") or "").strip().lower()
        if search:
            conditions.append("(lower(actor) LIKE ? OR lower(action) LIKE ? OR lower(entity_type) LIKE ? OR lower(entity_label) LIKE ? OR lower(outcome) LIKE ?)")
            like = f"%{search}%"
            params.extend([like, like, like, like, like])
        sql = "SELECT * FROM general_audit"
        if conditions:
            sql += " WHERE " + " AND ".join(conditions)
        sql += " ORDER BY created_at DESC, id DESC LIMIT ?"
        params.append(limit)
        with self.lock, self.connect() as conn:
            rows = conn.execute(sql, tuple(params)).fetchall()
            return [self._decode_general_audit(dict(row)) for row in rows]

    def _ensure_user_conn(self, conn: DatabaseConnection, username: str, password: str, role: str) -> None:
        now = datetime.now().isoformat(timespec="seconds")
        row = conn.execute("SELECT id FROM users WHERE username = ?", (username,)).fetchone()
        if row:
            return
        salt = secrets.token_hex(16)
        conn.execute(
            """
            INSERT INTO users (username, password_hash, salt, role, active, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (username, self._hash_password(password, salt), salt, role, True, now, now),
        )

    def authenticate_user(self, username: str, password: str) -> dict[str, Any] | None:
        return self.auth.authenticate(username, password)

    def create_session(self, username: str, ttl_hours: int = 24 * 30) -> str:
        return self.auth.create_session(username, ttl_hours)

    def get_user_by_username(self, username: str) -> dict[str, Any] | None:
        return self.auth.user_by_username(username)

    def get_user_by_session(self, token: str | None) -> dict[str, Any] | None:
        return self.auth.user_by_session(token)

    def delete_session(self, token: str | None) -> None:
        self.auth.delete_session(token)

    def _hash_password(self, password: str, salt: str) -> str:
        return AuthRepository.hash_password(password, salt)

    def _public_user(self, user: dict[str, Any]) -> dict[str, Any]:
        return AuthRepository.public_user(user)

    def _decode_event(self, row: dict[str, Any]) -> dict[str, Any]:
        row["delta"] = self._decode_json(row.pop("delta_json"))
        row["metadata"] = self._decode_json(row.pop("metadata_json"))
        return row

    def _decode_general_audit(self, row: dict[str, Any]) -> dict[str, Any]:
        row["details"] = self._decode_json(row.pop("details_json", {}))
        return row

    def _decode_json(self, value: Any) -> Any:
        if isinstance(value, str):
            return json.loads(value)
        return value

    def _json_param(self, value: Any) -> Any:
        if self.backend == "sqlite":
            return json.dumps(value, ensure_ascii=False, default=str)
        from psycopg.types.json import Jsonb

        return Jsonb(value, dumps=lambda item: json.dumps(item, ensure_ascii=False, default=str))





