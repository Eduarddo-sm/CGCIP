from __future__ import annotations

import os
import tempfile
import time
import unittest
from pathlib import Path

from services.backup_retention import BackupRetentionService


class BackupRetentionServiceTestCase(unittest.TestCase):
    def test_legacy_policy_is_upgraded_to_include_database_dumps(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            service = BackupRetentionService(Path(folder))
            service.save_policy({"extensions": [".xlsx"]})
            self.assertIn(".dump", service.policy()["extensions"])

    def test_database_retention_keeps_only_configured_latest_old_dumps(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            service = BackupRetentionService(Path(folder))
            service.save_policy({
                "database_retention_days": 1,
                "database_keep_latest": 2,
            })
            database_dir = service.backup_dir / "database"
            database_dir.mkdir()
            old_time = time.time() - (10 * 24 * 60 * 60)
            for index in range(3):
                path = database_dir / f"automatico_2026010{index + 1}_000000.dump"
                path.write_bytes(b"dump")
                os.utime(path, (old_time + index, old_time + index))
            result = service.cleanup()
            self.assertEqual(len(result["deleted"]), 1)
            self.assertEqual(len(list(database_dir.glob("*.dump"))), 2)


if __name__ == "__main__":
    unittest.main()
