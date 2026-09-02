from __future__ import annotations

import unittest

from services.diff_service import DiffService
from services.event_log_service import EventLogService
from services.overview_builder import OverviewBuilder


def table(headers, rows):
    return {
        "headers": headers,
        "rows": rows,
        "table_range": "A1:Z99",
    }


class MonitoringIntelligenceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.diff = DiffService()
        self.builder = OverviewBuilder()
        self.events = EventLogService(
            repo=object(),
            row_values=self.builder.row_values,
            normalized_value=self.builder.normalized_value,
            is_noop_change=self.builder.is_noop_change,
        )

    def test_empty_column_removal_does_not_create_change(self) -> None:
        before = table(
            ["NPJ", "TIPO DE LIQUIDAÇÃO"],
            [{"_row_id": 1, "NPJ": "123", "TIPO DE LIQUIDAÇÃO": ""}],
        )
        after = table(["NPJ"], [{"_row_id": 1, "NPJ": "123"}])

        delta = self.diff.compare(before, after, "NPJ")

        self.assertEqual(delta["changes"], [])
        self.assertEqual(delta["summary"]["columns_removed"], 0)

    def test_header_accents_case_and_spacing_are_equivalent(self) -> None:
        before = table(
            ["NPJ", "TIPO DE LIQUIDAÇÃO"],
            [{"_row_id": 1, "NPJ": "123", "TIPO DE LIQUIDAÇÃO": "TOTAL"}],
        )
        after = table(
            ["npj", " tipo  de liquidacao "],
            [{"_row_id": 1, "npj": "123", " tipo  de liquidacao ": "TOTAL"}],
        )

        delta = self.diff.compare(before, after, "NPJ")

        self.assertEqual(delta["changes"], [])
        self.assertFalse(delta["summary"]["structure_changed"])

    def test_completely_empty_rows_are_ignored(self) -> None:
        before = table(["NPJ", "CLIENTE"], [{"_row_id": 1, "NPJ": "123", "CLIENTE": "Cliente"}])
        after = table(
            ["NPJ", "CLIENTE"],
            [
                {"_row_id": 1, "NPJ": "123", "CLIENTE": "Cliente"},
                {"_row_id": 2, "NPJ": "", "CLIENTE": ""},
            ],
        )

        delta = self.diff.compare(before, after, "NPJ")

        self.assertEqual(delta["changes"], [])
        self.assertEqual(delta["summary"]["rows_added"], 0)

    def test_real_cell_change_is_preserved(self) -> None:
        before = table(["NPJ", "STATUS"], [{"_row_id": 1, "NPJ": "123", "STATUS": "PROPOSTA"}])
        after = table(["NPJ", "STATUS"], [{"_row_id": 1, "NPJ": "123", "STATUS": "PAGO"}])

        delta = self.diff.compare(before, after, "NPJ")

        self.assertEqual(len(delta["changes"]), 1)
        self.assertEqual(delta["changes"][0]["column"], "STATUS")
        self.assertEqual(delta["changes"][0]["before"], "PROPOSTA")
        self.assertEqual(delta["changes"][0]["after"], "PAGO")

    def test_legacy_empty_structural_event_is_hidden(self) -> None:
        event = {
            "event_type": "file_changed",
            "changes_count": 1,
            "delta": {
                "summary": {"columns_removed": 1, "columns_changed": 1},
                "changes": [{"type": "column_removed", "column": "TIPO DE LIQUIDAÇÃO"}],
            },
        }

        self.assertIsNone(self.events.sanitize_event_for_display(event))

    def test_meaningful_structural_change_has_useful_description(self) -> None:
        event = {
            "event_type": "file_changed",
            "changes_count": 1,
            "delta": {
                "summary": {"columns_removed": 1, "columns_changed": 1},
                "changes": [
                    {
                        "type": "column_removed",
                        "column": "TIPO DE LIQUIDAÇÃO",
                        "non_empty_values": 3,
                    }
                ],
            },
        }

        sanitized = self.events.sanitize_event_for_display(event)

        change = sanitized["delta"]["changes"][0]
        self.assertEqual(change["before"], "3 valores preenchidos")
        self.assertIsNone(change["after"])
        self.assertTrue(sanitized["delta"]["summary"]["structure_changed"])

    def test_cell_context_drops_empty_columns_but_keeps_client(self) -> None:
        event = {
            "event_type": "file_changed",
            "carteira": "GAMMA",
            "changes_count": 1,
            "delta": {
                "summary": {"cells_changed": 1},
                "changes": [
                    {
                        "type": "cell_changed",
                        "column": "STATUS",
                        "before": "PROPOSTA",
                        "after": "PAGO",
                        "row_before": {"NPJ": "123", "CLIENTE": "Cliente", "GECOR": "", "STATUS": "PROPOSTA"},
                        "row_after": {"NPJ": "123", "CLIENTE": "Cliente", "GECOR": "", "STATUS": "PAGO"},
                    }
                ],
            },
        }

        sanitized = self.events.sanitize_event_for_display(event)

        change = sanitized["delta"]["changes"][0]
        self.assertEqual(change["row_after"]["CLIENTE"], "Cliente")
        self.assertNotIn("GECOR", change["row_after"])

    def test_sanitizing_event_does_not_copy_shared_read_keys(self) -> None:
        class SharedReadKeys(set):
            def __deepcopy__(self, memo):
                raise AssertionError("read_keys must not be deep-copied per event")

        read_keys = SharedReadKeys({(event_id, 0) for event_id in range(10_000)})
        event = {
            "event_type": "file_changed",
            "read_keys": read_keys,
            "changes_count": 1,
            "delta": {
                "summary": {"cells_changed": 1},
                "changes": [
                    {
                        "type": "cell_changed",
                        "column": "STATUS",
                        "before": "PROPOSTA",
                        "after": "PAGO",
                    }
                ],
            },
        }

        sanitized = self.events.sanitize_event_for_display(event)

        self.assertIs(sanitized["read_keys"], read_keys)


if __name__ == "__main__":
    unittest.main()
