from __future__ import annotations

import unittest

from services.diff_service import DiffService
from services.system_negociador_service import SystemNegotiadorService


class FakeRepository:
    def __init__(self) -> None:
        self.negociador = {
            "id": 7,
            "nome": "negociador.beta",
            "negocial_username": "negociador.beta",
            "carteira": "GAMMA",
            "sheet": "Producao Diaria",
            "source_type": "sistema",
            "active": True,
            "last_mtime": "old-marker",
        }
        self.snapshot = {
            "id": 10,
            "content": self._table("Antes"),
        }
        self.created_snapshots = []

    def _table(self, client: str) -> dict:
        return {
            "file_path": "negocial://negociador.beta",
            "sheet": "Producao Diaria",
            "table_range": "Banco de dados",
            "headers": ["NPJ", "CLIENTE"],
            "types": {"NPJ": "text", "CLIENTE": "text"},
            "rows": [{"_row_id": 101, "NPJ": "123", "CLIENTE": client}],
            "row_count": 1,
        }

    def find_system_negociador(self, username: str):
        return self.negociador if username == "negociador.beta" else None

    def latest_snapshot(self, negociador_id: int, sheet: str):
        return self.snapshot

    def create_snapshot(self, negociador_id: int, sheet: str, table: dict) -> int:
        self.created_snapshots.append(table)
        self.snapshot = {"id": 11, "content": table}
        return 11

    def update_negociador(self, negociador_id: int, payload: dict) -> None:
        self.negociador.update(payload)


class FakeNegocial:
    def read_producao_table(self, username: str) -> dict:
        return FakeRepository()._table("Depois")

    def producao_marker(self, username: str) -> str:
        return "new-marker"


class FailOnEvent:
    def create_once(self, payload):
        raise AssertionError("Gerencial baseline must not create timeline events")


class SystemNegotiadorServiceTestCase(unittest.TestCase):
    def test_gerencial_change_updates_baseline_without_timeline_event(self) -> None:
        repo = FakeRepository()
        service = SystemNegotiadorService(
            repo,
            FakeNegocial(),
            DiffService(),
            FailOnEvent(),
            key_column_for_carteira=lambda carteira: "NPJ",
            bundle_factory=lambda negociador_id: {},
        )

        result = service.accept_current_as_baseline("negociador.beta")

        self.assertTrue(result["ok"])
        self.assertTrue(result["updated"])
        self.assertEqual(result["snapshot_id"], 11)
        self.assertEqual(repo.negociador["last_mtime"], "new-marker")
        self.assertEqual(repo.created_snapshots[0]["rows"][0]["CLIENTE"], "Depois")

        refresh = service.refresh(repo.negociador)
        self.assertFalse(refresh["changed"])

    def test_gerencial_operation_and_baseline_run_as_one_monitoring_transaction(self) -> None:
        repo = FakeRepository()
        service = SystemNegotiadorService(
            repo,
            FakeNegocial(),
            DiffService(),
            FailOnEvent(),
            key_column_for_carteira=lambda carteira: "NPJ",
            bundle_factory=lambda negociador_id: {},
        )

        result, baseline = service.execute_gerencial_change(lambda: {
            "ok": True,
            "affected_usernames": ["negociador.beta"],
        })

        self.assertTrue(result["ok"])
        self.assertTrue(baseline["ok"])
        self.assertEqual(baseline["updated"], 1)
        self.assertEqual(repo.negociador["last_mtime"], "new-marker")


if __name__ == "__main__":
    unittest.main()
