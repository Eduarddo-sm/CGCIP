from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any


DEFAULT_POLICY = {
    "snapshot_retention_days": 120,
    "snapshot_delete_limit": 5000,
    "read_retention_days": 180,
    "session_retention_days": 7,
    "monitoring_retention_days": 90,
}


@dataclass
class DatabaseTarget:
    schema: str
    table: str
    status: str
    owner: str
    notes: str


TABLE_CATALOG = [
    DatabaseTarget("gerencial", "users", "ativo", "gerencial", "Logins gerenciais."),
    DatabaseTarget("gerencial", "sessions", "manutencao", "gerencial", "Sessoes gerenciais; pode limpar expiradas."),
    DatabaseTarget("gerencial", "negociadores", "ativo", "gerencial", "Cadastro de negociadores por planilha ou sistema."),
    DatabaseTarget("gerencial", "carteiras", "ativo", "gerencial", "Carteiras do backoffice."),
    DatabaseTarget("gerencial", "events", "ativo", "monitoramento", "Eventos de timeline/overview."),
    DatabaseTarget("gerencial", "snapshots", "historico pesado", "monitoramento", "Snapshots completos; aplicar retencao segura."),
    DatabaseTarget("gerencial", "overview_reads", "manutencao", "overview", "Leitura individual por usuario."),
    DatabaseTarget("gerencial", "notification_reads", "manutencao", "notificacoes", "Notificacoes dispensadas por usuario."),
    DatabaseTarget("gerencial", "notes", "ativo", "gerencial", "Observacoes anexadas a itens."),
    DatabaseTarget("gerencial", "db_retention_policies", "governanca", "database", "Politica operacional de retencao do banco."),
    DatabaseTarget("gerencial", "data_quality_issues", "governanca", "database", "Fila de inconsistencias de qualidade para saneamento."),
    DatabaseTarget("gerencial", "database_health_snapshots", "observabilidade", "database", "Historico de saude, conexoes e performance do PostgreSQL."),
    DatabaseTarget("gerencial", "database_table_growth_snapshots", "observabilidade", "database", "Crescimento historico das tabelas operacionais."),
    DatabaseTarget("gerencial", "protocolos", "ativo", "protocolos", "Protocolos migrados da planilha para o banco."),
    DatabaseTarget("gerencial", "colchao_acordos", "ativo", "colchao", "Cadastro unificado dos acordos do colchao por carteira."),
    DatabaseTarget("gerencial", "colchao_parcelas", "ativo", "colchao", "Parcelas e estados operacionais do colchao por carteira."),
    DatabaseTarget("gerencial", "colchao_alpha", "legado", "colchao", "Base anterior mantida temporariamente apenas para auditoria da migracao."),
    DatabaseTarget("gerencial", "colchao_beta", "legado", "colchao", "Base anterior mantida temporariamente apenas para auditoria da migracao."),
    DatabaseTarget("negocial", "users", "ativo", "negocial", "Logins dos negociadores."),
    DatabaseTarget("negocial", "sessions", "manutencao", "negocial", "Sessoes negociais; pode limpar expiradas/revogadas."),
    DatabaseTarget("negocial", "pareceres", "ativo", "pareceres", "Solicitacoes de parecer do sistema negocial."),
    DatabaseTarget("negocial", "carteiras_negociais", "ativo", "carteiras", "Carteiras dinamicas negociais."),
    DatabaseTarget("negocial", "carteira_colunas", "ativo", "carteiras", "Definicao de colunas por carteira."),
    DatabaseTarget("negocial", "producao_registros", "alvo", "producao", "Tabela base recomendada para producao."),
    DatabaseTarget("negocial", "producao_gamma", "alvo", "producao", "Campos especificos do GAMMA."),
    DatabaseTarget("negocial", "producao_alpha", "alvo", "producao", "Campos especificos da Alpha."),
    DatabaseTarget("negocial", "producao_beta", "alvo", "producao", "Campos especificos da Beta."),
    DatabaseTarget("negocial", "producao_campos", "preparada", "producao", "Campos dinamicos para novas carteiras."),
    DatabaseTarget("negocial", "producao_gamma_gerencial", "ativo", "gerencial", "Complementos gerenciais do GAMMA."),
    DatabaseTarget("negocial", "producao_correcoes", "ativo", "correcoes", "Correcoes enviadas pelo backoffice."),
    DatabaseTarget("negocial", "alembic_version", "tecnica", "migrations", "Controle oficial de versao das migrations."),
    DatabaseTarget("negocial", "schema_migrations_meta", "tecnica", "migrations", "Marcador auxiliar da linha de base PostgreSQL."),
    DatabaseTarget("negocial", "db_retention_policies", "governanca", "database", "Politica operacional de retencao negocial."),
    DatabaseTarget("negocial", "data_quality_issues", "governanca", "database", "Fila de inconsistencias de qualidade negocial."),
]


class DatabaseMaintenanceService:
    def __init__(self, database_url: str) -> None:
        self.database_url = database_url

    def inventory(self) -> dict[str, Any]:
        with self._connect() as conn:
            tables = self._table_stats(conn)
        catalog = {
            f"{target.schema}.{target.table}": {
                "name": f"{target.schema}.{target.table}",
                "schema": target.schema,
                "table": target.table,
                "status": target.status,
                "owner": target.owner,
                "notes": target.notes,
            }
            for target in TABLE_CATALOG
        }
        for table in tables:
            catalog.setdefault(
                table["name"],
                {
                    "schema": table["schema"],
                    "table": table["table"],
                    "status": "nao catalogada",
                    "owner": "desconhecido",
                    "notes": "Tabela encontrada no banco, mas ainda nao documentada no catalogo.",
                },
            ).update(table)
        totals = {
            "tables": len(tables),
            "rows": sum(int(table.get("rows") or 0) for table in tables),
            "bytes": sum(int(table.get("bytes") or 0) for table in tables),
        }
        return {
            "ok": True,
            "generated_at": datetime.now().isoformat(timespec="seconds"),
            "totals": totals,
            "tables": sorted(catalog.values(), key=lambda item: (item["schema"], item["table"])),
            "recommendations": self._recommendations(catalog),
        }

    def cleanup(self, payload: dict[str, Any] | None = None) -> dict[str, Any]:
        payload = payload or {}
        policy = self._policy(payload)
        dry_run = bool(payload.get("dry_run", True))
        results: list[dict[str, Any]] = []
        with self._connect() as conn:
            results.append(self._expired_sessions(conn, "gerencial", policy["session_retention_days"], dry_run))
            results.append(self._expired_sessions(conn, "negocial", policy["session_retention_days"], dry_run))
            results.append(self._revoked_negocial_sessions(conn, policy["session_retention_days"], dry_run))
            results.append(self._old_notification_reads(conn, policy["read_retention_days"], dry_run))
            results.append(self._old_overview_reads(conn, policy["read_retention_days"], dry_run))
            results.append(self._orphan_overview_reads(conn, dry_run))
            results.append(self._old_unreferenced_snapshots(conn, policy["snapshot_retention_days"], policy["snapshot_delete_limit"], dry_run))
            results.append(self._old_monitoring_snapshots(conn, policy["monitoring_retention_days"], dry_run))
            results.append(self._old_table_growth_snapshots(conn, policy["monitoring_retention_days"], dry_run))
            if dry_run:
                conn.rollback()
            else:
                conn.commit()
        return {
            "ok": True,
            "dry_run": dry_run,
            "policy": policy,
            "results": results,
            "total_candidates": sum(int(item.get("candidates") or 0) for item in results),
            "total_deleted": 0 if dry_run else sum(int(item.get("deleted") or 0) for item in results),
        }

    def _connect(self):
        try:
            import psycopg
            from psycopg.rows import dict_row
        except ImportError as exc:
            raise RuntimeError("Manutencao do banco requer psycopg[binary].") from exc
        url = self.database_url.replace("postgresql+psycopg://", "postgresql://", 1)
        return psycopg.connect(url, row_factory=dict_row)

    def _policy(self, payload: dict[str, Any]) -> dict[str, int]:
        stored = self._stored_policy() if not payload.get("ignore_stored_policy") else {}
        policy = DEFAULT_POLICY | stored | {key: payload.get(key) for key in DEFAULT_POLICY if payload.get(key) is not None}
        return {
            "snapshot_retention_days": max(30, int(policy["snapshot_retention_days"])),
            "snapshot_delete_limit": max(100, int(policy["snapshot_delete_limit"])),
            "read_retention_days": max(30, int(policy["read_retention_days"])),
            "session_retention_days": max(1, int(policy["session_retention_days"])),
            "monitoring_retention_days": max(7, int(policy["monitoring_retention_days"])),
        }

    def _stored_policy(self) -> dict[str, int]:
        try:
            with self._connect() as conn:
                rows = conn.execute(
                    """
                    SELECT scope, retention_days, keep_latest
                    FROM "gerencial"."db_retention_policies"
                    WHERE enabled = TRUE
                    """
                ).fetchall()
        except Exception:
            return {}
        scopes = {str(row["scope"]): row for row in rows}
        result: dict[str, int] = {}
        if "snapshots" in scopes:
            result["snapshot_retention_days"] = int(scopes["snapshots"]["retention_days"])
            if int(scopes["snapshots"].get("keep_latest") or 0) > 0:
                result["snapshot_delete_limit"] = int(scopes["snapshots"]["keep_latest"])
        if "reads" in scopes:
            result["read_retention_days"] = int(scopes["reads"]["retention_days"])
        if "sessions" in scopes:
            result["session_retention_days"] = int(scopes["sessions"]["retention_days"])
        if "monitoring" in scopes:
            result["monitoring_retention_days"] = int(scopes["monitoring"]["retention_days"])
        return result

    def _table_stats(self, conn) -> list[dict[str, Any]]:
        rows = conn.execute(
            """
            SELECT n.nspname AS schema_name,
                   c.relname AS table_name,
                   pg_total_relation_size(c.oid) AS bytes
            FROM pg_class c
            JOIN pg_namespace n ON n.oid = c.relnamespace
            WHERE n.nspname IN ('gerencial', 'negocial') AND c.relkind = 'r'
            ORDER BY n.nspname, c.relname
            """
        ).fetchall()
        result = []
        for row in rows:
            schema = row["schema_name"]
            table = row["table_name"]
            count = conn.execute(f'SELECT count(*) AS total FROM "{schema}"."{table}"').fetchone()["total"]
            result.append({
                "name": f"{schema}.{table}",
                "schema": schema,
                "table": table,
                "rows": int(count),
                "bytes": int(row["bytes"] or 0),
                "size": self._format_bytes(int(row["bytes"] or 0)),
            })
        return result

    def _expired_sessions(self, conn, schema: str, retention_days: int, dry_run: bool) -> dict[str, Any]:
        cutoff = datetime.now() - timedelta(days=retention_days)
        sql = f'DELETE FROM "{schema}"."sessions" WHERE expires_at < %s'
        return self._delete_or_count(conn, f"{schema}.sessions expiradas", sql, (cutoff,), dry_run)

    def _revoked_negocial_sessions(self, conn, retention_days: int, dry_run: bool) -> dict[str, Any]:
        cutoff = datetime.now() - timedelta(days=retention_days)
        sql = 'DELETE FROM "negocial"."sessions" WHERE revoked_at IS NOT NULL AND revoked_at < %s'
        return self._delete_or_count(conn, "negocial.sessions revogadas antigas", sql, (cutoff,), dry_run)

    def _old_notification_reads(self, conn, retention_days: int, dry_run: bool) -> dict[str, Any]:
        cutoff = datetime.now() - timedelta(days=retention_days)
        sql = 'DELETE FROM "gerencial"."notification_reads" WHERE read_at < %s'
        return self._delete_or_count(conn, "gerencial.notification_reads antigas", sql, (cutoff,), dry_run)

    def _old_overview_reads(self, conn, retention_days: int, dry_run: bool) -> dict[str, Any]:
        cutoff = datetime.now() - timedelta(days=retention_days)
        sql = """
            DELETE FROM "gerencial"."overview_reads" r
            USING "gerencial"."events" e
            WHERE e.id = r.event_id AND e.changed_at < %s
        """
        return self._delete_or_count(conn, "gerencial.overview_reads de eventos antigos", sql, (cutoff,), dry_run)

    def _orphan_overview_reads(self, conn, dry_run: bool) -> dict[str, Any]:
        sql = """
            DELETE FROM "gerencial"."overview_reads" r
            WHERE NOT EXISTS (
                SELECT 1 FROM "gerencial"."events" e WHERE e.id = r.event_id
            )
        """
        return self._delete_or_count(conn, "gerencial.overview_reads orfas", sql, (), dry_run)

    def _old_unreferenced_snapshots(self, conn, retention_days: int, limit: int, dry_run: bool) -> dict[str, Any]:
        cutoff = datetime.now() - timedelta(days=retention_days)
        base = """
            WITH keep AS (
                SELECT snapshot_before_id AS id FROM "gerencial"."events" WHERE snapshot_before_id IS NOT NULL
                UNION
                SELECT snapshot_after_id AS id FROM "gerencial"."events" WHERE snapshot_after_id IS NOT NULL
                UNION
                SELECT MAX(id) AS id
                FROM "gerencial"."snapshots"
                GROUP BY negociador_id, sheet, date_trunc('month', captured_at)
            ),
            doomed AS (
                SELECT s.id
                FROM "gerencial"."snapshots" s
                WHERE s.captured_at < %s
                  AND NOT EXISTS (SELECT 1 FROM keep WHERE keep.id = s.id)
                ORDER BY s.id
                LIMIT %s
            )
        """
        if dry_run:
            count = conn.execute(base + " SELECT count(*) AS total FROM doomed", (cutoff, limit)).fetchone()["total"]
            return {"target": "gerencial.snapshots antigos sem referencia", "dry_run": True, "candidates": int(count), "deleted": 0}
        rows = conn.execute(base + ' DELETE FROM "gerencial"."snapshots" s USING doomed WHERE s.id = doomed.id RETURNING s.id', (cutoff, limit)).fetchall()
        return {"target": "gerencial.snapshots antigos sem referencia", "dry_run": False, "candidates": len(rows), "deleted": len(rows)}

    def _old_monitoring_snapshots(self, conn, retention_days: int, dry_run: bool) -> dict[str, Any]:
        cutoff = datetime.now() - timedelta(days=retention_days)
        sql = 'DELETE FROM "gerencial"."database_health_snapshots" WHERE captured_at < %s'
        return self._delete_or_count(conn, "gerencial.database_health_snapshots antigos", sql, (cutoff,), dry_run)

    def _old_table_growth_snapshots(self, conn, retention_days: int, dry_run: bool) -> dict[str, Any]:
        cutoff = datetime.now() - timedelta(days=retention_days)
        sql = 'DELETE FROM "gerencial"."database_table_growth_snapshots" WHERE captured_at < %s'
        return self._delete_or_count(conn, "gerencial.database_table_growth_snapshots antigos", sql, (cutoff,), dry_run)

    def _delete_or_count(self, conn, target: str, delete_sql: str, params: tuple[Any, ...], dry_run: bool) -> dict[str, Any]:
        if dry_run:
            conn.execute("SAVEPOINT maintenance_probe")
            rows = conn.execute(delete_sql + " RETURNING 1", params).fetchall()
            conn.execute("ROLLBACK TO SAVEPOINT maintenance_probe")
            total = len(rows)
            return {"target": target, "dry_run": True, "candidates": int(total), "deleted": 0}
        rows = conn.execute(delete_sql + " RETURNING 1", params).fetchall()
        return {"target": target, "dry_run": False, "candidates": len(rows), "deleted": len(rows)}

    def _recommendations(self, catalog: dict[str, dict[str, Any]]) -> list[str]:
        recommendations = [
            "Manter schemas gerencial e negocial separados; isso ja esta correto.",
            "Usar producao_registros + tabelas especificas por carteira como modelo alvo.",
            "Manter producao_registros + tabelas especificas por carteira como fonte operacional da producao.",
            "Executar manutencao dry_run antes de aplicar limpeza real.",
        ]
        snapshots = catalog.get("gerencial.snapshots", {})
        if int(snapshots.get("rows") or 0) > 50000:
            recommendations.append("Snapshots estao grandes; aplicar retencao de snapshots antigos sem referencia.")
        return recommendations

    def _format_bytes(self, value: int) -> str:
        units = ["B", "KB", "MB", "GB"]
        size = float(value)
        for unit in units:
            if size < 1024 or unit == units[-1]:
                return f"{size:.1f} {unit}" if unit != "B" else f"{int(size)} B"
            size /= 1024
