from __future__ import annotations

import os
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from services.database_backup import DatabaseBackupService


class DatabaseBackupRotationTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.service = DatabaseBackupService(
            "postgresql://usuario:senha@localhost:5432/projeto_negocial",
            Path(self.temp_dir.name),
        )

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def _write_dump(self, name: str, age_seconds: int) -> Path:
        path = self.service.backup_dir / name
        path.write_bytes(name.encode("utf-8"))
        timestamp = time.time() - age_seconds
        os.utime(path, (timestamp, timestamp))
        return path

    def test_successful_backup_deletes_exactly_the_oldest_dump(self) -> None:
        oldest = self._write_dump("automatico_20260101_000000.dump", 300)
        newest = self._write_dump("automatico_20260102_000000.dump", 200)

        def fake_run(command: list[str], _parsed: dict[str, str]) -> None:
            target = Path(command[command.index("--file") + 1])
            target.write_bytes(b"new-valid-dump")

        with (
            patch.object(self.service, "_require_binary", return_value="pg_dump"),
            patch.object(self.service, "_run", side_effect=fake_run),
        ):
            result = self.service.create_backup("automatico")

        self.assertFalse(oldest.exists())
        self.assertTrue(newest.exists())
        self.assertEqual(len(list(self.service.backup_dir.glob("*.dump"))), 2)
        self.assertEqual(result["deleted_backup"]["name"], oldest.name)

    def test_failed_backup_keeps_existing_dumps(self) -> None:
        oldest = self._write_dump("automatico_20260101_000000.dump", 300)

        with (
            patch.object(self.service, "_require_binary", return_value="pg_dump"),
            patch.object(self.service, "_run", side_effect=RuntimeError("falha simulada")),
        ):
            with self.assertRaisesRegex(RuntimeError, "falha simulada"):
                self.service.create_backup("automatico")

        self.assertTrue(oldest.exists())
        self.assertEqual(list(self.service.backup_dir.glob("*.dump")), [oldest])

    def test_rotation_preserves_restore_target(self) -> None:
        restore_target = self._write_dump("restaurar_20260101_000000.dump", 300)
        removable = self._write_dump("automatico_20260102_000000.dump", 200)

        deleted = self.service._delete_oldest_backup(protected_names={restore_target.name})

        self.assertTrue(restore_target.exists())
        self.assertFalse(removable.exists())
        self.assertEqual(deleted["name"], removable.name)

    def test_storage_location_is_persisted_and_existing_backups_can_move(self) -> None:
        existing = self._write_dump("automatico_20260101_000000.dump", 300)
        target = Path(self.temp_dir.name) / "destino-personalizado"

        result = self.service.configure_storage(str(target), migrate_existing=True)
        reloaded = DatabaseBackupService(
            "postgresql://usuario:senha@localhost:5432/projeto_negocial",
            Path(self.temp_dir.name),
        )

        self.assertFalse(existing.exists())
        self.assertTrue((target / existing.name).exists())
        self.assertEqual(result["moved_backups"], 1)
        self.assertEqual(reloaded.backup_dir.resolve(), target.resolve())
        self.assertTrue(reloaded.storage_config()["writable"])

    def test_storage_location_must_be_absolute(self) -> None:
        with self.assertRaisesRegex(RuntimeError, "caminho absoluto"):
            self.service.configure_storage("backup-relativo")

    def test_verify_backup_checks_dump_and_returns_checksum(self) -> None:
        target = self._write_dump("projeto_negocial_20260101_000000.dump", 0)

        with (
            patch.object(self.service, "_require_binary", return_value="pg_restore"),
            patch.object(self.service, "_run") as run,
        ):
            result = self.service.verify_backup(target.name)

        self.assertTrue(result["ok"])
        self.assertEqual(result["name"], target.name)
        self.assertEqual(len(result["sha256"]), 64)
        run.assert_called_once()

    def test_list_backups_identifies_origin(self) -> None:
        self._write_dump("automatico_20260101_000000.dump", 3)
        self._write_dump("pre_restore_20260101_000001.dump", 2)
        self._write_dump("projeto_negocial_20260101_000002.dump", 1)

        sources = {item["name"]: item["source"] for item in self.service.list_backups()["items"]}

        self.assertEqual(sources["automatico_20260101_000000.dump"], "automatic")
        self.assertEqual(sources["pre_restore_20260101_000001.dump"], "pre_restore")
        self.assertEqual(sources["projeto_negocial_20260101_000002.dump"], "manual")


if __name__ == "__main__":
    unittest.main()
