from datetime import date
from types import SimpleNamespace
import unittest

from backend.services.producao_service import _next_month_dynamic_system_values


class ProducaoNextMonthTest(unittest.TestCase):
    def test_dynamic_fields_use_clone_state(self) -> None:
        clone = SimpleNamespace(
            data_acordo=date(2026, 8, 1),
            status="PROPOSTA",
        )
        user = SimpleNamespace(username="negociador.alpha")

        values = _next_month_dynamic_system_values(clone, user)

        self.assertEqual(values["DATA"], date(2026, 8, 1))
        self.assertEqual(values["DATA_ACORDO"], date(2026, 8, 1))
        self.assertEqual(values["STATUS"], "PROPOSTA")
        self.assertEqual(values["JUSTIFICATIVA"], "")
        self.assertIsNone(values["DATA_DO_PAGAMENTO"])
        self.assertEqual(values["NEGOCIADOR"], "negociador.alpha")


if __name__ == "__main__":
    unittest.main()
