from decimal import Decimal
from types import SimpleNamespace
import unittest

from fastapi import HTTPException

from backend.services.producao_service import _automatic_dynamic_value, _coerce_dynamic_value


class ProducaoMoneyTest(unittest.TestCase):
    def test_localized_money_is_converted_without_losing_cents(self):
        column = SimpleNamespace(tipo="moeda", nome="VALOR DO ACORDO")

        _, numeric_value, _, _ = _coerce_dynamic_value(column, "R$ 90.169,87")

        self.assertEqual(numeric_value, Decimal("90169.87"))

    def test_invalid_numeric_value_returns_validation_error(self):
        column = SimpleNamespace(tipo="numero", nome="DIAS DE ATRASO")

        with self.assertRaises(HTTPException) as context:
            _coerce_dynamic_value(column, "usuario.teste")

        self.assertEqual(context.exception.status_code, 422)
        self.assertIn("valor numerico valido", context.exception.detail)

    def test_username_automation_is_ignored_for_numeric_columns(self):
        column = SimpleNamespace(automatico=True, auto_tipo="usuario", tipo="numero")
        user = SimpleNamespace(username="usuario.teste", carteira="GAMMA")

        self.assertIsNone(_automatic_dynamic_value(column, user))

    def test_username_automation_is_kept_for_text_columns(self):
        column = SimpleNamespace(automatico=True, auto_tipo="usuario", tipo="texto")
        user = SimpleNamespace(username="usuario.teste", carteira="GAMMA")

        self.assertEqual(_automatic_dynamic_value(column, user), "usuario.teste")


if __name__ == "__main__":
    unittest.main()
