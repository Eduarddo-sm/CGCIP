import unittest

from services.negocial_production_mixin import NegocialProductionMixin
from services.negocial_reporting_mixin import NegocialReportingMixin
from services.negocial_service import NegocialService


class NegocialServiceStructureTestCase(unittest.TestCase):
    def setUp(self):
        self.service = object.__new__(NegocialService)

    def test_production_operations_are_provided_by_domain_mixin(self):
        self.assertIs(NegocialService.read_producao_table, NegocialProductionMixin.read_producao_table)
        self.assertEqual(self.service._header_key("Honorarios recebidos"), "HONORARIOS_RECEBIDOS")

    def test_gerencial_queries_do_not_own_monthly_auto_break(self):
        self.assertFalse(hasattr(NegocialProductionMixin, "_auto_break_previous_month_production_postgres"))
        self.assertFalse(hasattr(NegocialProductionMixin, "_auto_break_previous_month_production_sqlite"))

    def test_reporting_and_closing_are_provided_by_domain_mixin(self):
        self.assertIs(NegocialService.producao_mensal, NegocialReportingMixin.producao_mensal)
        self.assertEqual(self.service._validate_month("07"), 7)
        with self.assertRaises(ValueError):
            self.service._validate_month(13)

    def test_schema_status_uses_official_record_status(self):
        column = {"nome": "STATUS", "chave": "STATUS"}
        value = self.service._schema_column_value(
            column,
            row={},
            base={"STATUS": "Proposta negada"},
            field_values={"STATUS": "Proposta"},
        )
        self.assertEqual(value, "Proposta negada")

    def test_schema_justificativa_uses_official_record_value(self):
        column = {"nome": "JUSTIFICATIVA", "chave": "JUSTIFICATIVA"}
        value = self.service._schema_column_value(
            column,
            row={},
            base={"JUSTIFICATIVA": "Cliente recusou a proposta"},
            field_values={"JUSTIFICATIVA": ""},
        )
        self.assertEqual(value, "Cliente recusou a proposta")


if __name__ == "__main__":
    unittest.main()
