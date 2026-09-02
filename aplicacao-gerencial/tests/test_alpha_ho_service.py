from __future__ import annotations

import unittest
from datetime import date
from decimal import Decimal

from services.alpha_ho_rules import dias_de_atraso, honorarios_base


class AlphaHonorariosServiceTestCase(unittest.TestCase):
    def test_installment_agreement_uses_entry_as_honorarios_base(self) -> None:
        value, source = honorarios_base(
            {
                "tipo_acordo": "PARCELADO",
                "valor_total_acordo": Decimal("10000.00"),
                "valor_entrada": Decimal("1500.00"),
            }
        )
        self.assertEqual(value, Decimal("1500.00"))
        self.assertEqual(source, "VALOR_DA_ENTRADA")

    def test_sight_agreement_uses_total_as_honorarios_base(self) -> None:
        value, source = honorarios_base(
            {
                "tipo_acordo": "A_VISTA",
                "valor_total_acordo": Decimal("10000.00"),
                "valor_entrada": Decimal("0.00"),
            }
        )
        self.assertEqual(value, Decimal("10000.00"))
        self.assertEqual(source, "VALOR_DO_ACORDO")

    def test_sight_agreement_accepts_display_label(self) -> None:
        value, source = honorarios_base(
            {
                "tipo_acordo": "À vista",
                "valor_total_acordo": Decimal("8500.00"),
                "valor_entrada": Decimal("900.00"),
            }
        )
        self.assertEqual(value, Decimal("8500.00"))
        self.assertEqual(source, "VALOR_DO_ACORDO")

    def test_paid_agreement_freezes_delay_on_payment_date(self) -> None:
        self.assertEqual(
            dias_de_atraso(
                date(2023, 11, 16),
                "PAGAMENTO_REALIZADO",
                date(2026, 8, 6),
                hoje=date(2026, 8, 10),
            ),
            994,
        )

    def test_awaiting_writeoff_freezes_delay_on_payment_date(self) -> None:
        self.assertEqual(
            dias_de_atraso(
                date(2023, 11, 16),
                "Aguardando baixa",
                date(2026, 8, 6),
                hoje=date(2026, 8, 10),
            ),
            994,
        )

    def test_open_agreement_uses_current_date(self) -> None:
        self.assertEqual(
            dias_de_atraso(
                date(2023, 11, 16),
                "AGUARDANDO_PAGAMENTO",
                date(2026, 8, 6),
                hoje=date(2026, 8, 10),
            ),
            998,
        )


if __name__ == "__main__":
    unittest.main()
