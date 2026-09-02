from __future__ import annotations

import unittest
from decimal import Decimal

from services.carteira_schema_service import CarteiraSchemaService
from services.negocial_service import NegocialService


class CarteiraSchemaServiceTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.service = CarteiraSchemaService({
            "PROPOSTA": "Proposta",
            "PAGAMENTO_REALIZADO": "Pagamento realizado",
        })

    def test_status_options_accept_objects_labels_and_remove_duplicates(self) -> None:
        result = self.service.normalize_options(
            ["Proposta", {"label": "Pagamento realizado"}, {"value": "PROPOSTA"}],
            "STATUS",
        )
        self.assertEqual(result, ["PROPOSTA", "PAGAMENTO_REALIZADO"])

    def test_gamma_ho_defaults_to_ten_percent(self) -> None:
        result = self.service.normalize_ho_rules({}, "GAMMA")
        self.assertEqual(result["percentual_ho_padrao"], Decimal("10"))
        self.assertTrue(result["calculo_automatico_ho"])

    def test_invalid_ho_interval_is_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "minimo"):
            self.service.normalize_ho_rules(
                {"usa_percentual_ho": True, "percentual_ho_minimo": 12, "percentual_ho_maximo": 10},
                "CUSTOM",
            )

    def test_beta_ho_rule_has_explicit_twenty_two_percent_bindings(self) -> None:
        result = self.service.normalize_ho_rules(
            {
                "usa_percentual_ho": True,
                "percentual_ho_padrao": 22,
                "percentual_ho_minimo": 22,
                "percentual_ho_maximo": 22,
                "calculo_automatico_ho": True,
            },
            "BETA",
        )
        self.assertEqual(result["coluna_base"], "VALOR_TOTAL_DE_ACORDO")
        self.assertEqual(result["coluna_destino"], "HONORARIOS")

    def test_conditional_ho_rule_keeps_distinct_sight_and_installment_bases(self) -> None:
        result = self.service.normalize_ho_rules(
            {
                "usa_percentual_ho": True,
                "calculo_automatico_ho": True,
                "motor_calculo": "PERCENTUAL_CONDICIONAL",
                "percentual_ho_padrao": 10,
                "coluna_base_vista": "VALOR_TOTAL",
                "coluna_base_parcelado": "VALOR_ENTRADA",
                "coluna_destino": "HONORARIOS",
            },
            "CUSTOM",
        )
        self.assertEqual(result["motor_calculo"], "PERCENTUAL_CONDICIONAL")
        self.assertEqual(result["coluna_base_vista"], "VALOR_TOTAL")
        self.assertEqual(result["coluna_base_parcelado"], "VALOR_ENTRADA")

    def test_exceptional_engine_is_restricted_to_alpha(self) -> None:
        with self.assertRaisesRegex(ValueError, "Alpha"):
            self.service.normalize_ho_rules(
                {
                    "usa_percentual_ho": True,
                    "motor_calculo": "ALPHA_EXCEPCIONAL",
                },
                "BETA",
            )

    def test_alpha_exceptional_rule_keeps_conditional_bases(self) -> None:
        result = self.service.normalize_ho_rules(
            {
                "usa_percentual_ho": True,
                "calculo_automatico_ho": True,
                "motor_calculo": "ALPHA_EXCEPCIONAL",
            },
            "ALPHA",
        )
        self.assertEqual(result["coluna_base_vista"], "VALOR_TOTAL")
        self.assertEqual(result["coluna_base_parcelado"], "ENTRADA")
        self.assertEqual(result["coluna_destino"], "HONORARIOS_CALCULADOS")

    def test_automatic_ho_rule_requires_explicit_bindings(self) -> None:
        with self.assertRaisesRegex(ValueError, "coluna"):
            self.service.normalize_ho_rules(
                {
                    "usa_percentual_ho": True,
                    "percentual_ho_padrao": 5,
                    "calculo_automatico_ho": True,
                },
                "CUSTOM",
            )

    def test_ho_rule_rejects_non_numeric_binding(self) -> None:
        service = NegocialService.__new__(NegocialService)
        with self.assertRaisesRegex(ValueError, "numerica ou monetaria"):
            service._ho_rule_params(
                {
                    "usa_percentual_ho": True,
                    "calculo_automatico_ho": True,
                    "coluna_base": "CLIENTE",
                    "coluna_destino": "HONORARIOS",
                    "percentual_ho_padrao": Decimal("10"),
                    "percentual_ho_minimo": Decimal("10"),
                    "percentual_ho_maximo": Decimal("10"),
                    "casas_decimais": 2,
                },
                {
                    "CLIENTE": {"id": 1, "tipo": "texto"},
                    "HONORARIOS": {"id": 2, "tipo": "moeda"},
                },
            )

    def test_schema_versions_accept_postgres_jsonb_objects(self) -> None:
        service = NegocialService.__new__(NegocialService)
        result = service._schema_versions_payload(
            {"id": 1, "nome": "GAMMA", "slug": "GAMMA"},
            [{
                "id": 2,
                "version_number": 1,
                "action": "migration_gamma_schema",
                "created_at": "2026-07-14",
                "schema_json": {"carteira": {"modo_schema": True}, "colunas": [{"chave": "NPJ"}]},
            }],
        )
        snapshot = result["items"][0]["schema"]
        self.assertTrue(snapshot["carteira"]["modo_schema"])
        self.assertEqual(snapshot["colunas"][0]["chave"], "NPJ")

    def test_schema_column_visibility_is_preserved(self) -> None:
        service = NegocialService.__new__(NegocialService)
        service.schema_service = self.service
        columns = service._normalize_carteira_columns([
            {"nome": "IDENTIFICADOR", "tipo": "texto", "identificador": True},
            {"nome": "CAMPO INTERNO", "tipo": "texto", "visivel": False},
            {"nome": "JUSTIFICATIVA", "tipo": "texto"},
        ])

        by_key = {column["chave"]: column for column in columns}
        self.assertFalse(by_key["CAMPO_INTERNO"]["visivel"])
        self.assertFalse(by_key["JUSTIFICATIVA"]["visivel"])
        self.assertTrue(by_key["DATA"]["visivel"])

    def test_existing_schema_key_is_not_rebuilt_from_display_name(self) -> None:
        service = NegocialService.__new__(NegocialService)
        service.schema_service = self.service
        columns = service._normalize_carteira_columns([
            {
                "nome": "PARCELADO OU A VISTA",
                "chave": "PARCELADO_OU_VISTA",
                "tipo": "select",
                "identificador": True,
                "opcoes": ["A VISTA", "PARCELADO"],
            },
        ])

        preserved = next(column for column in columns if column["nome"] == "PARCELADO OU A VISTA")
        self.assertEqual(preserved["chave"], "PARCELADO_OU_VISTA")

    def test_multiselect_column_and_options_are_preserved(self) -> None:
        service = NegocialService.__new__(NegocialService)
        service.schema_service = self.service
        columns = service._normalize_carteira_columns([{
            "nome": "SERVICOS",
            "chave": "SERVICOS",
            "tipo": "multiselect",
            "identificador": True,
            "opcoes": ["Parecer", "Evento", "Reuniao"],
        }])

        services = next(column for column in columns if column["chave"] == "SERVICOS")
        self.assertEqual(services["tipo"], "multiselect")
        self.assertEqual(services["opcoes"], ["Parecer", "Evento", "Reuniao"])

    def test_multiselect_value_is_normalized_and_validated(self) -> None:
        service = NegocialService.__new__(NegocialService)
        column = {
            "nome": "SERVICOS",
            "tipo": "multiselect",
            "opcoes_json": ["Parecer", "Evento", "Reuniao"],
        }
        self.assertEqual(
            service._validate_dynamic_column_value(column, ["evento", "Parecer", "evento"]),
            ["Evento", "Parecer"],
        )
        with self.assertRaisesRegex(ValueError, "opcoes validas"):
            service._validate_dynamic_column_value(column, ["Opcao inexistente"])

    def test_percent_column_is_not_discarded_during_deduplication(self) -> None:
        service = NegocialService.__new__(NegocialService)
        service.schema_service = self.service
        columns = service._normalize_carteira_columns([
            {"nome": "NPJ", "chave": "NPJ", "tipo": "texto", "identificador": True},
            {"nome": "%", "chave": "PERCENTUAL", "tipo": "numero"},
        ])

        self.assertIn("PERCENTUAL", {column["chave"] for column in columns})

    def test_standard_aliases_do_not_create_duplicate_columns(self) -> None:
        service = NegocialService.__new__(NegocialService)
        service.schema_service = self.service
        columns = service._normalize_carteira_columns([
            {"nome": "NPJ", "chave": "NPJ", "tipo": "texto", "identificador": True},
            {"nome": "DATA ACORDO", "chave": "DATA_ACORDO", "tipo": "data"},
            {"nome": "CLIENTE", "chave": "CLIENTE", "tipo": "texto"},
            {"nome": "PARCELADO OU A VISTA", "chave": "PARCELADO_OU_VISTA", "tipo": "select"},
            {"nome": "STATUS", "chave": "STATUS", "tipo": "select"},
            {"nome": "JUSTIFICATIVA", "chave": "JUSTIFICATIVA", "tipo": "texto"},
            {"nome": "NEGOCIADOR", "chave": "NEGOCIADOR", "tipo": "texto"},
        ])

        keys = {column["chave"] for column in columns}
        self.assertNotIn("DATA", keys)
        self.assertNotIn("TIPO_DE_ACORDO", keys)


if __name__ == "__main__":
    unittest.main()
