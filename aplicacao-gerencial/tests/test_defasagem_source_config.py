from __future__ import annotations

import tempfile
import unittest
from dataclasses import replace
from pathlib import Path

from services.defasagem_service import DefasagemService


class DefasagemSourceConfigTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.default = self.root / "default"
        self.default.mkdir()
        self.service = DefasagemService()
        self.service.settings = replace(
            self.service.settings,
            default_excel_path=self.default / "contratos_ativos.xlsx",
            default_garantias_path=self.default / "garantias.xlsx",
            default_gatilhos_path=self.default / "gatilhos.xlsx",
        )
        self.service.source_config_path = self.root / "source_directory.json"

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def test_configures_readable_directory_and_reports_files(self) -> None:
        source = self.root / "source"
        source.mkdir()
        for name in ("contratos_ativos.xlsx", "garantias.xlsx", "gatilhos.xlsx"):
            (source / name).write_bytes(b"xlsx")

        result = self.service.configure_source_directory(str(source))

        self.assertTrue(result["ok"])
        self.assertEqual(Path(result["source"]["path"]), source.resolve())
        self.assertTrue(result["source"]["files"]["contracts"]["exists"])
        self.assertTrue(result["source"]["files"]["guarantees"]["exists"])
        self.assertTrue(result["source"]["files"]["triggers"]["exists"])

    def test_rejects_directory_without_contracts_workbook(self) -> None:
        source = self.root / "empty"
        source.mkdir()

        with self.assertRaises(RuntimeError) as raised:
            self.service.configure_source_directory(str(source))

        self.assertIn("contratos_ativos.xlsx", str(raised.exception))
        self.assertFalse(self.service.source_config_path.exists())


if __name__ == "__main__":
    unittest.main()
