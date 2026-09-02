from __future__ import annotations

import os
import hashlib
import json
from datetime import datetime, timezone
from typing import Any, Callable


class DatabaseMonitoringService:
    def __init__(self, database_url: str, pool_stats_provider: Callable[[], dict[str, Any]] | None = None) -> None:
        self.database_url = database_url
        self.pool_stats_provider = pool_stats_provider or (lambda: {})
        self.connection_warning_percent = float(os.environ.get("GERENCIAL_DB_CONNECTION_WARNING_PERCENT", "75"))
        self.cache_warning_percent = float(os.environ.get("GERENCIAL_DB_CACHE_WARNING_PERCENT", "95"))
        self.long_transaction_seconds = int(os.environ.get("GERENCIAL_DB_LONG_TRANSACTION_SECONDS", "60"))
        self.dead_tuple_warning_percent = float(os.environ.get("GERENCIAL_DB_DEAD_TUPLE_WARNING_PERCENT", "20"))
        self.heartbeat_warning_seconds = int(os.environ.get("GERENCIAL_DB_HEARTBEAT_WARNING_SECONDS", "900"))

    def collect(self) -> dict[str, Any]:
        with self._connect() as conn:
            database = self._database_metrics(conn)
            tables = self._table_metrics(conn)
            previous = self._previous_table_sizes(conn)
            for table in tables:
                old_size = int(previous.get(table["name"], 0))
                table["previous_size_bytes"] = old_size
                table["growth_bytes"] = int(table["size_bytes"]) - old_size if old_size else 0
                table["growth_percent"] = round((table["growth_bytes"] / old_size) * 100, 2) if old_size else 0.0
            pool = self._safe_pool_stats()
            alerts = self.evaluate_alerts(database, tables)
            snapshot_id = self._persist(conn, database, tables, pool, alerts)
            self._sync_alerts(conn, alerts, database["captured_at"])
            conn.commit()
        return {
            "ok": True,
            "snapshot_id": snapshot_id,
            "captured_at": database["captured_at"],
            "database": database,
            "pool": pool,
            "alerts": alerts,
            "tables": tables,
        }

    def latest(self) -> dict[str, Any]:
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT id, captured_at, database_size_bytes, max_connections,
                       total_connections, active_connections, idle_connections,
                       cache_hit_percent, transactions_committed, transactions_rolled_back,
                       deadlocks, temp_bytes, waiting_locks, long_transactions,
                       slowest_transaction_seconds, pool_stats_json, alerts_json
                FROM gerencial.database_health_snapshots
                ORDER BY captured_at DESC, id DESC
                LIMIT 1
                """
            ).fetchone()
            if not row:
                return {"ok": True, "snapshot": None}
            tables = conn.execute(
                """
                SELECT schema_name, table_name, row_estimate, dead_rows, size_bytes,
                       growth_bytes, growth_percent, captured_at
                FROM gerencial.database_table_growth_snapshots
                WHERE health_snapshot_id = %s
                ORDER BY size_bytes DESC
                """,
                (row["id"],),
            ).fetchall()
        return {
            "ok": True,
            "snapshot": {
                "id": row["id"],
                "captured_at": row["captured_at"],
                "database": {
                    key: row[key]
                    for key in (
                        "database_size_bytes", "max_connections", "total_connections",
                        "active_connections", "idle_connections", "cache_hit_percent",
                        "transactions_committed", "transactions_rolled_back", "deadlocks",
                        "temp_bytes", "waiting_locks", "long_transactions",
                        "slowest_transaction_seconds",
                    )
                },
                "pool": row["pool_stats_json"] or {},
                "alerts": row["alerts_json"] or [],
                "tables": [dict(item) for item in tables],
            },
        }

    def history(self, limit: int = 96) -> dict[str, Any]:
        safe_limit = max(1, min(int(limit), 1000))
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT id, captured_at, database_size_bytes, total_connections,
                       active_connections, cache_hit_percent, waiting_locks,
                       long_transactions, alerts_json
                FROM gerencial.database_health_snapshots
                ORDER BY captured_at DESC, id DESC
                LIMIT %s
                """,
                (safe_limit,),
            ).fetchall()
        return {"ok": True, "items": [dict(row) for row in rows]}

    def status(self) -> dict[str, Any]:
        payload = self.latest()
        snapshot = payload.get("snapshot")
        if not snapshot:
            return {"ok": False, "status": "unknown", "heartbeat": "missing", "age_seconds": None}
        captured_at = snapshot.get("captured_at")
        captured = captured_at if isinstance(captured_at, datetime) else datetime.fromisoformat(str(captured_at))
        if captured.tzinfo is None:
            captured = captured.replace(tzinfo=timezone.utc)
        age_seconds = max(0, int((datetime.now(timezone.utc) - captured.astimezone(timezone.utc)).total_seconds()))
        heartbeat = "stale" if age_seconds > self.heartbeat_warning_seconds else "healthy"
        return {
            "ok": heartbeat == "healthy",
            "status": "degraded" if heartbeat == "stale" else "healthy",
            "heartbeat": heartbeat,
            "age_seconds": age_seconds,
            "warning_after_seconds": self.heartbeat_warning_seconds,
            "captured_at": captured_at,
            "open_alerts": self.list_alerts("open", 100).get("total", 0),
        }

    def list_alerts(self, status: str = "active", limit: int = 100) -> dict[str, Any]:
        safe_limit = max(1, min(int(limit), 500))
        status = str(status or "active").strip().lower()
        where = "WHERE status IN ('open', 'acknowledged')" if status == "active" else "WHERE status = %s"
        params: tuple[Any, ...] = () if status == "active" else (status,)
        with self._connect() as conn:
            rows = conn.execute(
                f"""
                SELECT id, fingerprint, alert_type, severity, message, source, status,
                       details_json, first_seen_at, last_seen_at, occurrence_count,
                       acknowledged_by, acknowledged_at, resolved_at
                FROM gerencial.database_alerts
                {where}
                ORDER BY CASE severity WHEN 'critical' THEN 0 WHEN 'warning' THEN 1 ELSE 2 END,
                         last_seen_at DESC
                LIMIT %s
                """,
                (*params, safe_limit),
            ).fetchall()
        return {"ok": True, "status": status, "total": len(rows), "items": [dict(row) for row in rows]}

    def acknowledge_alert(self, alert_id: int, username: str) -> dict[str, Any]:
        with self._connect() as conn:
            row = conn.execute(
                """
                UPDATE gerencial.database_alerts
                SET status = CASE WHEN source = 'manual_test' THEN 'resolved' ELSE 'acknowledged' END,
                    acknowledged_by = %s,
                    acknowledged_at = NOW(),
                    resolved_at = CASE WHEN source = 'manual_test' THEN NOW() ELSE resolved_at END
                WHERE id = %s AND status = 'open'
                RETURNING id, status, acknowledged_by, acknowledged_at
                """,
                (str(username or "admin"), int(alert_id)),
            ).fetchone()
            conn.commit()
        if not row:
            raise ValueError("Alerta aberto nao encontrado.")
        return {"ok": True, "alert": dict(row)}

    def create_test_alert(self, username: str) -> dict[str, Any]:
        alert = {
            "severity": "warning",
            "type": "test",
            "message": "Alerta de teste do monitoramento operacional.",
            "source": "manual_test",
            "details": {"requested_by": str(username or "admin"), "test": True},
        }
        now = datetime.now(timezone.utc)
        with self._connect() as conn:
            self._sync_alerts(conn, [alert], now, resolve_missing=False)
            row = conn.execute(
                "SELECT * FROM gerencial.database_alerts WHERE fingerprint = %s",
                (self._alert_fingerprint(alert),),
            ).fetchone()
            conn.commit()
        return {"ok": True, "alert": dict(row)}

    def performance(self, limit: int = 20) -> dict[str, Any]:
        safe_limit = max(1, min(int(limit), 100))
        with self._connect() as conn:
            extension = conn.execute(
                """
                SELECT name, default_version, installed_version,
                       installed_version IS NOT NULL AS installed
                FROM pg_available_extensions
                WHERE name = 'pg_stat_statements'
                """
            ).fetchone()
            migrations = conn.execute(
                """
                SELECT table_schema, version_num
                FROM (
                    SELECT 'gerencial'::text AS table_schema,
                           (SELECT version_num FROM gerencial.alembic_version LIMIT 1) AS version_num
                    UNION ALL
                    SELECT 'negocial'::text,
                           (SELECT version_num FROM negocial.alembic_version LIMIT 1)
                ) versions
                """
            ).fetchall()
            tables = conn.execute(
                """
                SELECT schemaname AS schema_name, relname AS table_name,
                       seq_scan, seq_tup_read, idx_scan, idx_tup_fetch,
                       n_live_tup AS row_estimate, n_dead_tup AS dead_rows,
                       last_analyze, last_autoanalyze
                FROM pg_stat_user_tables
                WHERE schemaname IN ('gerencial', 'negocial')
                ORDER BY seq_tup_read DESC, seq_scan DESC
                LIMIT %s
                """,
                (safe_limit,),
            ).fetchall()
            indexes = conn.execute(
                """
                SELECT schemaname AS schema_name, relname AS table_name, indexrelname AS index_name,
                       idx_scan, pg_relation_size(indexrelid) AS size_bytes
                FROM pg_stat_user_indexes
                WHERE schemaname IN ('gerencial', 'negocial')
                  AND indexrelname NOT LIKE '%%_pkey'
                ORDER BY idx_scan ASC, pg_relation_size(indexrelid) DESC
                LIMIT %s
                """,
                (safe_limit,),
            ).fetchall()
            invalid_indexes = conn.execute(
                """
                SELECT n.nspname AS schema_name, c.relname AS index_name
                FROM pg_index i
                JOIN pg_class c ON c.oid = i.indexrelid
                JOIN pg_namespace n ON n.oid = c.relnamespace
                WHERE n.nspname IN ('gerencial', 'negocial') AND NOT i.indisvalid
                ORDER BY n.nspname, c.relname
                """
            ).fetchall()
            top_queries: list[dict[str, Any]] = []
            query_stats_error = ""
            if extension and extension["installed"]:
                try:
                    top_queries = [dict(row) for row in conn.execute(
                        """
                        SELECT queryid, calls, rows,
                               ROUND(total_exec_time::numeric, 2) AS total_exec_time_ms,
                               ROUND(mean_exec_time::numeric, 2) AS mean_exec_time_ms,
                               LEFT(regexp_replace(query, '\\s+', ' ', 'g'), 500) AS query
                        FROM pg_stat_statements
                        WHERE dbid = (SELECT oid FROM pg_database WHERE datname = current_database())
                        ORDER BY total_exec_time DESC
                        LIMIT %s
                        """,
                        (safe_limit,),
                    ).fetchall()]
                except Exception as exc:
                    conn.rollback()
                    query_stats_error = str(exc)
        extension_payload = dict(extension) if extension else {"name": "pg_stat_statements", "installed": False}
        extension_payload["loaded"] = bool(extension_payload.get("installed") and not query_stats_error)
        recommendations = self._performance_recommendations(extension_payload, tables, indexes, invalid_indexes, query_stats_error)
        return {
            "ok": True,
            "captured_at": datetime.now(timezone.utc),
            "migrations": [dict(row) for row in migrations],
            "pg_stat_statements": extension_payload,
            "query_stats_error": query_stats_error,
            "top_queries": top_queries,
            "table_access": [dict(row) for row in tables],
            "low_usage_indexes": [dict(row) for row in indexes],
            "invalid_indexes": [dict(row) for row in invalid_indexes],
            "recommendations": recommendations,
        }

    def _connect(self):
        try:
            import psycopg
            from psycopg.rows import dict_row
        except ImportError as exc:
            raise RuntimeError("Monitoramento do PostgreSQL requer psycopg[binary].") from exc
        url = self.database_url.replace("postgresql+psycopg://", "postgresql://", 1)
        if not url.startswith("postgresql://"):
            raise RuntimeError("Monitoramento operacional esta disponivel apenas para PostgreSQL.")
        return psycopg.connect(url, row_factory=dict_row)

    def _database_metrics(self, conn) -> dict[str, Any]:
        row = conn.execute(
            """
            SELECT NOW() AS captured_at,
                   pg_database_size(current_database()) AS database_size_bytes,
                   current_setting('max_connections')::int AS max_connections,
                   COUNT(*) FILTER (WHERE pid <> pg_backend_pid()) AS total_connections,
                   COUNT(*) FILTER (WHERE state = 'active' AND pid <> pg_backend_pid()) AS active_connections,
                   COUNT(*) FILTER (WHERE state = 'idle' AND pid <> pg_backend_pid()) AS idle_connections,
                   COUNT(*) FILTER (WHERE wait_event_type IS NOT NULL AND pid <> pg_backend_pid()) AS waiting_connections,
                   COUNT(*) FILTER (
                       WHERE xact_start IS NOT NULL
                         AND NOW() - xact_start > make_interval(secs => %s)
                         AND pid <> pg_backend_pid()
                   ) AS long_transactions,
                   COALESCE(MAX(EXTRACT(EPOCH FROM (NOW() - xact_start))) FILTER (
                       WHERE xact_start IS NOT NULL AND pid <> pg_backend_pid()
                   ), 0) AS slowest_transaction_seconds
            FROM pg_stat_activity
            WHERE datname = current_database()
            """,
            (self.long_transaction_seconds,),
        ).fetchone()
        stats = conn.execute(
            """
            SELECT CASE WHEN blks_hit + blks_read = 0 THEN 100
                        ELSE ROUND((100.0 * blks_hit / (blks_hit + blks_read))::numeric, 2) END AS cache_hit_percent,
                   xact_commit AS transactions_committed,
                   xact_rollback AS transactions_rolled_back,
                   deadlocks,
                   temp_bytes
            FROM pg_stat_database
            WHERE datname = current_database()
            """
        ).fetchone()
        waiting_locks = conn.execute("SELECT count(*) AS total FROM pg_locks WHERE NOT granted").fetchone()["total"]
        payload = dict(row)
        payload.update(dict(stats or {}))
        payload["waiting_locks"] = int(waiting_locks or 0)
        payload["connection_usage_percent"] = round(
            (int(payload["total_connections"] or 0) / max(1, int(payload["max_connections"] or 1))) * 100,
            2,
        )
        payload["slowest_transaction_seconds"] = round(float(payload["slowest_transaction_seconds"] or 0), 2)
        return payload

    @staticmethod
    def _table_metrics(conn) -> list[dict[str, Any]]:
        rows = conn.execute(
            """
            SELECT s.schemaname AS schema_name,
                   s.relname AS table_name,
                   s.n_live_tup::bigint AS row_estimate,
                   s.n_dead_tup::bigint AS dead_rows,
                   pg_total_relation_size(c.oid)::bigint AS size_bytes,
                   s.last_analyze,
                   s.last_autoanalyze
            FROM pg_stat_user_tables s
            JOIN pg_class c ON c.relname = s.relname
            JOIN pg_namespace n ON n.oid = c.relnamespace AND n.nspname = s.schemaname
            WHERE s.schemaname IN ('gerencial', 'negocial')
            ORDER BY pg_total_relation_size(c.oid) DESC
            """
        ).fetchall()
        result = []
        for row in rows:
            item = dict(row)
            item["name"] = f"{item['schema_name']}.{item['table_name']}"
            live = max(0, int(item["row_estimate"] or 0))
            dead = max(0, int(item["dead_rows"] or 0))
            item["dead_tuple_percent"] = round((dead / max(1, live + dead)) * 100, 2)
            result.append(item)
        return result

    @staticmethod
    def _previous_table_sizes(conn) -> dict[str, int]:
        rows = conn.execute(
            """
            SELECT DISTINCT ON (schema_name, table_name)
                   schema_name, table_name, size_bytes
            FROM gerencial.database_table_growth_snapshots
            ORDER BY schema_name, table_name, captured_at DESC, id DESC
            """
        ).fetchall()
        return {f"{row['schema_name']}.{row['table_name']}": int(row["size_bytes"] or 0) for row in rows}

    def evaluate_alerts(self, database: dict[str, Any], tables: list[dict[str, Any]]) -> list[dict[str, Any]]:
        alerts: list[dict[str, Any]] = []
        usage = float(database.get("connection_usage_percent") or 0)
        if usage >= self.connection_warning_percent:
            alerts.append({"severity": "critical" if usage >= 90 else "warning", "type": "connections", "message": f"Uso de conexoes em {usage:.1f}%."})
        cache = float(database.get("cache_hit_percent") or 100)
        if cache < self.cache_warning_percent:
            alerts.append({"severity": "warning", "type": "cache", "message": f"Cache hit em {cache:.1f}%, abaixo de {self.cache_warning_percent:.1f}%."})
        long_transactions = int(database.get("long_transactions") or 0)
        if long_transactions:
            alerts.append({"severity": "warning", "type": "long_transactions", "message": f"{long_transactions} transacao(oes) acima de {self.long_transaction_seconds}s."})
        waiting_locks = int(database.get("waiting_locks") or 0)
        if waiting_locks:
            alerts.append({"severity": "critical", "type": "locks", "message": f"{waiting_locks} lock(s) aguardando liberacao."})
        for table in tables:
            dead_percent = float(table.get("dead_tuple_percent") or 0)
            dead_rows = int(table.get("dead_rows") or 0)
            if dead_rows >= 1000 and dead_percent >= self.dead_tuple_warning_percent:
                alerts.append({
                    "severity": "warning",
                    "type": "dead_tuples",
                    "table": table["name"],
                    "message": f"{table['name']} com {dead_percent:.1f}% de linhas mortas.",
                })
        return alerts

    @staticmethod
    def _performance_recommendations(extension, tables, indexes, invalid_indexes, query_stats_error: str = "") -> list[dict[str, str]]:
        items: list[dict[str, str]] = []
        if not extension or not extension.get("installed"):
            items.append({
                "severity": "warning",
                "type": "extension",
                "message": "Ative pg_stat_statements para medir as consultas mais custosas pelo tempo real acumulado.",
            })
        elif not extension.get("loaded"):
            items.append({
                "severity": "warning",
                "type": "extension_restart",
                "message": "pg_stat_statements foi instalado; reinicie o servico PostgreSQL como administrador para concluir o pre-carregamento.",
            })
        if invalid_indexes:
            items.append({"severity": "critical", "type": "invalid_indexes", "message": f"Ha {len(invalid_indexes)} indice(s) invalido(s)."})
        high_seq = [row for row in tables if int(row["seq_tup_read"] or 0) >= 100000 and int(row["seq_scan"] or 0) > int(row["idx_scan"] or 0)]
        if high_seq:
            names = ", ".join(f"{row['schema_name']}.{row['table_name']}" for row in high_seq[:4])
            items.append({"severity": "warning", "type": "sequential_scans", "message": f"Revisar filtros e indices em: {names}."})
        large_unused = [row for row in indexes if int(row["idx_scan"] or 0) == 0 and int(row["size_bytes"] or 0) >= 10 * 1024 * 1024]
        if large_unused:
            items.append({"severity": "info", "type": "unused_indexes", "message": f"Validar {len(large_unused)} indice(s) grande(s) ainda sem uso medido."})
        if not items:
            items.append({"severity": "success", "type": "healthy", "message": "Nenhum gargalo estrutural evidente nas estatisticas atuais."})
        return items

    @staticmethod
    def _alert_fingerprint(alert: dict[str, Any]) -> str:
        stable = {
            "type": alert.get("type"),
            "table": alert.get("table"),
            "source": alert.get("source", "database_monitoring"),
        }
        return hashlib.sha256(json.dumps(stable, sort_keys=True).encode("utf-8")).hexdigest()

    def _sync_alerts(self, conn, alerts: list[dict[str, Any]], seen_at: datetime, resolve_missing: bool = True) -> None:
        from psycopg.types.json import Jsonb

        fingerprints: list[str] = []
        for alert in alerts:
            fingerprint = self._alert_fingerprint(alert)
            fingerprints.append(fingerprint)
            details = dict(alert.get("details") or {})
            if alert.get("table"):
                details["table"] = alert["table"]
            conn.execute(
                """
                INSERT INTO gerencial.database_alerts (
                    fingerprint, alert_type, severity, message, source, status,
                    details_json, first_seen_at, last_seen_at
                ) VALUES (%s, %s, %s, %s, %s, 'open', %s, %s, %s)
                ON CONFLICT (fingerprint) DO UPDATE SET
                    severity = EXCLUDED.severity,
                    message = EXCLUDED.message,
                    details_json = EXCLUDED.details_json,
                    last_seen_at = EXCLUDED.last_seen_at,
                    occurrence_count = gerencial.database_alerts.occurrence_count + 1,
                    status = CASE WHEN gerencial.database_alerts.status = 'resolved' THEN 'open'
                                  ELSE gerencial.database_alerts.status END,
                    resolved_at = NULL
                """,
                (
                    fingerprint, alert.get("type", "unknown"), alert.get("severity", "warning"),
                    alert.get("message", "Alerta de banco"), alert.get("source", "database_monitoring"),
                    Jsonb(details), seen_at, seen_at,
                ),
            )
        if not resolve_missing:
            return
        if fingerprints:
            conn.execute(
                """
                UPDATE gerencial.database_alerts
                SET status = 'resolved', resolved_at = %s
                WHERE source = 'database_monitoring'
                  AND status IN ('open', 'acknowledged')
                  AND NOT (fingerprint = ANY(%s))
                """,
                (seen_at, fingerprints),
            )
        else:
            conn.execute(
                """
                UPDATE gerencial.database_alerts
                SET status = 'resolved', resolved_at = %s
                WHERE source = 'database_monitoring' AND status IN ('open', 'acknowledged')
                """,
                (seen_at,),
            )

    def _persist(self, conn, database: dict[str, Any], tables: list[dict[str, Any]], pool: dict[str, Any], alerts: list[dict[str, Any]]) -> int:
        from psycopg.types.json import Jsonb

        row = conn.execute(
            """
            INSERT INTO gerencial.database_health_snapshots (
                captured_at, database_size_bytes, max_connections, total_connections,
                active_connections, idle_connections, cache_hit_percent,
                transactions_committed, transactions_rolled_back, deadlocks, temp_bytes,
                waiting_locks, long_transactions, slowest_transaction_seconds,
                pool_stats_json, alerts_json
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING id
            """,
            (
                database["captured_at"], database["database_size_bytes"], database["max_connections"],
                database["total_connections"], database["active_connections"], database["idle_connections"],
                database["cache_hit_percent"], database["transactions_committed"], database["transactions_rolled_back"],
                database["deadlocks"], database["temp_bytes"], database["waiting_locks"],
                database["long_transactions"], database["slowest_transaction_seconds"], Jsonb(pool), Jsonb(alerts),
            ),
        ).fetchone()
        snapshot_id = int(row["id"])
        cursor = conn.cursor()
        cursor.executemany(
            """
            INSERT INTO gerencial.database_table_growth_snapshots (
                health_snapshot_id, schema_name, table_name, row_estimate, dead_rows,
                size_bytes, growth_bytes, growth_percent, captured_at
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            [
                (
                    snapshot_id, table["schema_name"], table["table_name"], table["row_estimate"],
                    table["dead_rows"], table["size_bytes"], table["growth_bytes"],
                    table["growth_percent"], database["captured_at"],
                )
                for table in tables
            ],
        )
        return snapshot_id

    def _safe_pool_stats(self) -> dict[str, Any]:
        try:
            return dict(self.pool_stats_provider() or {})
        except Exception as exc:
            return {"error": str(exc)}
