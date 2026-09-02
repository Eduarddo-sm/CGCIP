from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from services.colchao_service import ColchaoError, ColchaoService


class ColchaoDueDateTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.service = ColchaoService(Path(self.temp_dir.name))

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_batch_change_normalizes_due_date_without_requiring_status(self) -> None:
        changes = self.service._normalize_batch_changes(
            [{"row": 12, "vencimento": "2026-08-20"}]
        )

        self.assertEqual(
            changes,
            [{"row": 12, "observacao": "", "vencimento": "20/08/2026"}],
        )

    def test_batch_change_rejects_invalid_due_date(self) -> None:
        with self.assertRaisesRegex(ColchaoError, "Data de vencimento invalida"):
            self.service._normalize_batch_changes(
                [{"row": 12, "vencimento": "31/02/2026"}]
            )

    def test_due_date_change_keeps_the_profile_date_header(self) -> None:
        record = {
            "__row_number": 7,
            "__sheet_name": "ATIVO",
            "SUITID": "ABC-1",
            "NOME": "Cliente Teste",
            "ACORDO": "2",
            "COND PARCELADAS": "3/10",
            "MES": "15/08/2026",
        }

        change = self.service._planned_due_date_change(
            [record], 7, "2026-09-15", "gestor.teste", "beta"
        )

        self.assertIsNotNone(change)
        self.assertEqual(change["header"], "MES")
        self.assertEqual(change["antes"], "15/08/2026")
        self.assertEqual(change["depois"], "15/09/2026")

    def test_reschedule_skips_paid_installments_and_rebuilds_schedule(self) -> None:
        rows = [
            self._installment(2, "1/3", "10/08/2026", "A VENCER"),
            self._installment(3, "2/3", "10/09/2026", "PAGO"),
            self._installment(4, "3/3", "10/10/2026", "VENCIDO"),
        ]

        plan = self.service._plan_due_date_reschedule(
            rows,
            {"row": 2, "sheet": "COLCHAO", "scope": "all_open", "mode": "schedule", "new_date": "20/08/2026"},
            "gestor.teste",
            "alpha",
        )

        self.assertEqual(plan["total"], 2)
        self.assertEqual([item["row"] for item in plan["changes"]], [2, 4])
        self.assertEqual([item["depois"] for item in plan["changes"]], ["20/08/2026", "20/09/2026"])

    def test_change_day_clamps_to_last_day_of_month(self) -> None:
        rows = [
            self._installment(2, "1/2", "10/02/2026", "A VENCER"),
            self._installment(3, "2/2", "10/03/2026", "A VENCER"),
        ]

        plan = self.service._plan_due_date_reschedule(
            rows,
            {"row": 2, "sheet": "COLCHAO", "scope": "all_open", "mode": "day", "new_date": "31/01/2026"},
            "gestor.teste",
            "alpha",
        )

        self.assertEqual([item["depois"] for item in plan["changes"]], ["28/02/2026", "31/03/2026"])

    def test_clients_groups_installments_by_agreement(self) -> None:
        rows = [
            self._installment(2, "1/2", "10/08/2026", "A VENCER"),
            self._installment(3, "2/2", "10/09/2026", "PAGO"),
            {**self._installment(4, "1/1", "10/10/2026", "QUEBRA"), "ACORDO": "2"},
        ]
        self.service._profile_records = lambda _profile: rows

        result = self.service.clients("alpha")

        self.assertEqual(result["total"], 1)
        self.assertEqual(result["agreements"], 2)
        self.assertEqual(result["items"][0]["agreement_count"], 2)
        self.assertEqual(result["items"][0]["installment_count"], 3)

    @staticmethod
    def _installment(row: int, parcel: str, due: str, status: str) -> dict:
        return {
            "__row_number": row,
            "__sheet_name": "COLCHAO",
            "DEBIT ID": "52578941",
            "CLIENTE": "Cliente Teste",
            "CPF/CNPJ": "12345678900",
            "OPERADOR": "Operador",
            "ACORDO": "1",
            "PARCELAS": parcel,
            "VALOR DO ACORDO": "100,00",
            "DATA DO VENCIMENTO": due,
            "STATUS": status,
        }


if __name__ == "__main__":
    unittest.main()
