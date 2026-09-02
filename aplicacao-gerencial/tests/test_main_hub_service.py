from __future__ import annotations

import unittest
from types import SimpleNamespace

from services.main_hub_service import MainHubService


class MainHubServiceTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.service = MainHubService(
            SimpleNamespace(list_items=lambda username, status: [{"id": "ALT_1_0", "lido": False, "usuario": username}]),
            SimpleNamespace(read_pendentes=lambda: [{"PK": "42"}]),
            SimpleNamespace(pending_records=lambda: [{"row": 7, "STATUS": "PENDENTE"}]),
            SimpleNamespace(list_open_notifications=lambda limit: [{"id": 9, "tool_id": 2}]),
        )

    def test_aggregates_hub_domains(self) -> None:
        payload = self.service.payload("gestor")
        self.assertTrue(payload["changed"])
        self.assertEqual(len(payload["overview"]), 1)
        self.assertEqual(len(payload["pareceres"]), 1)
        self.assertEqual(len(payload["protocolos"]), 1)
        self.assertEqual(len(payload["ferramentas"]), 1)

    def test_matching_version_omits_unchanged_payload(self) -> None:
        first = self.service.payload("gestor")
        second = self.service.payload("gestor", first["version"])
        self.assertEqual(second, {"changed": False, "version": first["version"]})


if __name__ == "__main__":
    unittest.main()
