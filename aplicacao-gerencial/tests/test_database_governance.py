from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from database.repository import Repository
from scripts.verify_backup_restore import _transform_restore_sql
from services.database_backup import DatabaseBackupService
from services.database_monitoring import DatabaseMonitoringService
from scripts.load_test import RequestMetric, summarize


class DatabaseGovernanceTestCase(unittest.TestCase):
    def test_alert_fingerprint_is_stable_when_metric_value_changes(self) -> None:
        service = DatabaseMonitoringService("postgresql://unused")
        first = {"type": "connections", "severity": "warning", "message": "Uso em 76%."}
        second = {"type": "connections", "severity": "critical", "message": "Uso em 92%."}
        self.assertEqual(service._alert_fingerprint(first), service._alert_fingerprint(second))

    def test_load_slo_separates_authentication_from_business_requests(self) -> None:
        metrics = [
            RequestMetric("gerencial", "/api/login", 1000, True, 200),
            RequestMetric("gerencial", "/api/me", 100, True, 200),
            RequestMetric("negocial", "/api/producao", 150, True, 200),
        ]
        result = summarize(metrics, 1, 1, 500, 1500, 1, 1)
        self.assertTrue(result["ok"])
        self.assertLessEqual(result["business_p95_ms"], 500)
        self.assertLessEqual(result["auth_p95_ms"], 1500)

    def test_sqlite_schema_contains_monitoring_and_retention_tables(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            repository = Repository(f"sqlite:///{(Path(folder) / 'db.sqlite3').as_posix()}")
            with repository.connect() as conn:
                names = {
                    row["name"]
                    for row in conn.execute(
                        "SELECT name FROM sqlite_master WHERE type = 'table'"
                    ).fetchall()
                }
                policy = conn.execute(
                    "SELECT retention_days FROM db_retention_policies WHERE scope = ?",
                    ("monitoring",),
                ).fetchone()
            self.assertIn("database_health_snapshots", names)
            self.assertIn("database_table_growth_snapshots", names)
            self.assertEqual(policy["retention_days"], 90)

    def test_monitoring_alerts_cover_operational_risks(self) -> None:
        service = DatabaseMonitoringService("postgresql://unused")
        database = {
            "connection_usage_percent": 92,
            "cache_hit_percent": 80,
            "long_transactions": 2,
            "waiting_locks": 1,
        }
        tables = [{"name": "negocial.producao_registros", "dead_rows": 2000, "dead_tuple_percent": 25}]

        alert_types = {item["type"] for item in service.evaluate_alerts(database, tables)}

        self.assertEqual(alert_types, {"connections", "cache", "long_transactions", "locks", "dead_tuples"})

    def test_restore_sql_rewrites_schema_without_changing_copy_data(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            source = Path(folder) / "source.sql"
            target = Path(folder) / "target.sql"
            source.write_text(
                "CREATE TABLE gerencial.events (value text);\n"
                "COPY gerencial.events (value) FROM stdin;\n"
                "gerencial negocial\n"
                "\\.\n"
                "CREATE TABLE negocial.users (id integer);\n",
                encoding="utf-8",
            )

            _transform_restore_sql(source, target, {"gerencial": "restore_g", "negocial": "restore_n"})
            transformed = target.read_text(encoding="utf-8")

            self.assertIn("CREATE TABLE restore_g.events", transformed)
            self.assertIn("CREATE TABLE restore_n.users", transformed)
            self.assertIn("gerencial negocial", transformed)

    def test_backup_sha256_is_stable(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "backup.dump"
            path.write_bytes(b"backup-test")
            self.assertEqual(
                DatabaseBackupService._sha256(path),
                "77cbfd6833aba5c2b3e6442ebe6ed7bad77e419c129192ffcb598722028efa7c",
            )


if __name__ == "__main__":
    unittest.main()
