from datetime import date
from decimal import Decimal

from fastapi import HTTPException
import unittest
from unittest.mock import patch

from backend.models import CarteiraNegocial, ProducaoRegistro, User
from backend.schemas.producao import ProducaoCreate
from backend.services import producao_service


def _payload(**overrides):
    values = {
        "npj": "20250000000000",
        "cliente": "Cliente",
        "gecor": "4962",
        "valor_total_acordo": "1000,00",
        "valor_entrada": "200,00",
        "valor_ho": "100,00",
        "tipo_acordo": "PARCELADO",
        "data_vencimento": date.today(),
        "status": "PROPOSTA",
    }
    values.update(overrides)
    return ProducaoCreate(**values)


class ProducaoBusinessRulesTest(unittest.TestCase):
    def test_manual_ho_cannot_exceed_wallet_maximum(self):
        wallet = CarteiraNegocial(
            nome="GAMMA",
            slug="GAMMA",
            usa_percentual_ho=True,
            percentual_ho_maximo=Decimal("10"),
        )
        user = User(username="negociador", carteira="GAMMA", role="USER")
        with patch.object(producao_service, "_carteira_definition", return_value=wallet):
            with self.assertRaises(HTTPException) as raised:
                producao_service._validate_manual_ho_limit(
                    None,
                    _payload(valor_ho="100,01"),
                    user,
                    valor_total=Decimal("1000"),
                    valor_entrada=Decimal("200"),
                    raw_ho=Decimal("100.01"),
                )

        self.assertEqual(raised.exception.status_code, 422)
        self.assertIn("10%", raised.exception.detail)

    def test_previous_month_is_read_only(self):
        item = ProducaoRegistro(
            data_acordo=date(2020, 1, 15),
            competencia=date(2020, 1, 1),
            cliente="Cliente",
            valor_total_acordo=Decimal("100"),
            valor_entrada=Decimal("0"),
            tipo_acordo="A_VISTA",
            data_vencimento=date(2020, 1, 20),
            status="PROPOSTA",
            carteira="GAMMA",
            user_id=1,
        )

        with self.assertRaises(HTTPException) as raised:
            producao_service._ensure_current_month_editable(item)

        self.assertEqual(raised.exception.status_code, 409)

    def test_formalized_new_agreement_refreshes_agreement_date(self):
        item = ProducaoRegistro(
            data_acordo=date(2026, 8, 1),
            competencia=date(2026, 8, 1),
            cliente="Cliente",
            valor_total_acordo=Decimal("100"),
            valor_entrada=Decimal("0"),
            tipo_acordo="A_VISTA",
            data_vencimento=date(2026, 8, 10),
            status="QUEBRA",
            carteira="GAMMA",
            user_id=1,
        )

        changed = producao_service._apply_formalized_new_agreement(
            item,
            "QUEBRA",
            "AGUARDANDO_PAGAMENTO",
            True,
        )

        self.assertTrue(changed)
        self.assertEqual(item.data_acordo, date.today())
        self.assertEqual(item.competencia, date.today().replace(day=1))

    def test_formalized_new_agreement_rejects_invalid_transition(self):
        item = ProducaoRegistro(
            data_acordo=date.today(),
            competencia=date.today().replace(day=1),
            cliente="Cliente",
            valor_total_acordo=Decimal("100"),
            valor_entrada=Decimal("0"),
            tipo_acordo="A_VISTA",
            data_vencimento=date.today(),
            status="PROPOSTA",
            carteira="GAMMA",
            user_id=1,
        )

        with self.assertRaises(HTTPException) as raised:
            producao_service._apply_formalized_new_agreement(
                item,
                "PROPOSTA",
                "PAGAMENTO_REALIZADO",
                True,
            )

        self.assertEqual(raised.exception.status_code, 422)


if __name__ == "__main__":
    unittest.main()
