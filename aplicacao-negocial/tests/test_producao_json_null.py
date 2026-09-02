import unittest
from datetime import date
from types import SimpleNamespace
from unittest.mock import patch

from backend.models.producao import ProducaoCampo
from backend.services.producao_service import _sync_dynamic_system_fields


class ProducaoCampoJsonNullTests(unittest.TestCase):
    def test_absent_json_is_persisted_as_sql_null(self):
        column_type = ProducaoCampo.__table__.c.valor_json.type

        self.assertTrue(column_type.none_as_null)

    def test_existing_legacy_field_forces_json_null_normalization(self):
        column = SimpleNamespace(
            id=10,
            chave="DATA_DO_PAGAMENTO",
            tipo="data",
            nome="Data do pagamento",
        )
        field = SimpleNamespace(
            coluna_id=10,
            valor_texto=None,
            valor_numero=None,
            valor_data=None,
            valor_json=None,
        )
        item = SimpleNamespace(id=20, campos=[field])

        with (
            patch(
                "backend.services.producao_service._dynamic_columns",
                return_value=[column],
            ),
            patch("backend.services.producao_service.flag_modified") as mark_dirty,
        ):
            _sync_dynamic_system_fields(
                SimpleNamespace(),
                item,
                SimpleNamespace(),
                {"DATA_DO_PAGAMENTO": date(2026, 7, 21)},
            )

        self.assertEqual(field.valor_data, date(2026, 7, 21))
        self.assertIsNone(field.valor_json)
        mark_dirty.assert_called_once_with(field, "valor_json")


if __name__ == "__main__":
    unittest.main()
