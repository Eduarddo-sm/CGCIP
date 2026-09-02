from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from database.repository import Repository
from services.snapshot_retention import SnapshotRetentionService


class SnapshotRetentionServiceTest(unittest.TestCase):
    def test_keeps_event_snapshots_and_latest_baseline(self):
        with TemporaryDirectory() as temp_dir:
            repo = Repository(Path(temp_dir) / "test.sqlite3")
            negotiator_id = repo.create_negociador({
                "nome": "Teste",
                "arquivo_path": "teste.xlsx",
                "sheet": "Dados",
                "source_type": "planilha",
            })
            first = repo.create_snapshot(negotiator_id, "Dados", {"headers": [], "rows": []})
            referenced = repo.create_snapshot(negotiator_id, "Dados", {"headers": ["A"], "rows": [["1"]]})
            repo.create_event({
                "negociador_id": negotiator_id,
                "snapshot_before_id": first,
                "snapshot_after_id": referenced,
                "event_type": "file_changed",
                "sheet": "Dados",
                "file_path": "teste.xlsx",
                "changed_at": "2026-08-11T10:00:00",
                "changes_count": 1,
                "delta": {"changes": [{"type": "cell_changed"}]},
                "metadata": {},
            })
            repo.create_snapshot(negotiator_id, "Dados", {"headers": ["A"], "rows": [["1"]]})
            repo.create_snapshot(negotiator_id, "Dados", {"headers": ["A"], "rows": [["2"]]})

            service = SnapshotRetentionService(repo)
            self.assertEqual(service.inspect()["removable"], 1)
            result = service.cleanup()
            self.assertEqual(result["deleted"], 1)
            self.assertEqual(result["after"]["total"], 3)
            self.assertEqual(result["after"]["removable"], 0)
            repo.close()


if __name__ == "__main__":
    unittest.main()
