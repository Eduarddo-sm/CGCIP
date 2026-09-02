from __future__ import annotations

from pathlib import Path
import tempfile
import unittest

from services.attachment_storage import AttachmentStorageService


def service_in(tmp_path: Path) -> AttachmentStorageService:
    service = AttachmentStorageService()
    service.shared_data_dir = tmp_path / "shared"
    service.default_dir = service.shared_data_dir / "ferramenta-anexos"
    service.config_path = service.shared_data_dir / "ferramenta_attachment_storage.json"
    return service


class AttachmentStorageServiceTest(unittest.TestCase):
    def test_configure_storage_moves_existing_attachments(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            tmp_path = Path(folder)
            service = service_in(tmp_path)
            source = service.default_dir / "1" / "2" / "2026" / "08"
            source.mkdir(parents=True)
            (source / "arquivo.pdf").write_bytes(b"conteudo")
            target = tmp_path / "novo-destino"

            result = service.configure_storage(str(target), migrate_existing=True)

            self.assertEqual(result["moved_attachments"], 1)
            self.assertEqual((target / "1" / "2" / "2026" / "08" / "arquivo.pdf").read_bytes(), b"conteudo")
            self.assertFalse((source / "arquivo.pdf").exists())
            self.assertEqual(result["storage"]["legacy_paths"], [])

    def test_configure_storage_preserves_old_root_as_legacy(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            tmp_path = Path(folder)
            service = service_in(tmp_path)
            service.default_dir.mkdir(parents=True)
            (service.default_dir / "anterior.txt").write_text("ok", encoding="utf-8")
            target = tmp_path / "novo-destino"

            result = service.configure_storage(str(target), migrate_existing=False)

            self.assertEqual(result["moved_attachments"], 0)
            self.assertEqual(result["storage"]["legacy_paths"], [str(service.default_dir.resolve())])
            self.assertTrue((service.default_dir / "anterior.txt").exists())

    def test_rejects_destination_inside_current_storage(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            service = service_in(Path(folder))
            service.default_dir.mkdir(parents=True)
            with self.assertRaisesRegex(RuntimeError, "nao pode ficar dentro"):
                service.configure_storage(str(service.default_dir / "subpasta"), migrate_existing=True)


if __name__ == "__main__":
    unittest.main()
