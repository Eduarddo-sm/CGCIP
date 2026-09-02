import unittest
from datetime import date
from types import SimpleNamespace

from fastapi import HTTPException

from backend.schemas.ferramenta import FerramentaDefinitionInput
from backend.services.ferramenta_service import (
    _apply_calculated_fields,
    _condition_matches,
    _normalize_field_value,
    slugify,
    validate_payload,
    validate_definition,
)


class FerramentaServiceTest(unittest.TestCase):
    def test_automatic_date_is_filled_only_on_create(self):
        field = SimpleNamespace(
            chave="DATA",
            nome="Data",
            tipo="data",
            obrigatorio=True,
            somente_leitura=False,
            validacao_json={"preenchimento_automatico": "today"},
            condicao_json={},
            valor_padrao_json=None,
            opcoes_json=[],
        )
        version = SimpleNamespace(campos=[field])
        user = SimpleNamespace(username="teste", carteira="GAMMA")

        self.assertEqual(validate_payload(version, {}, user)["DATA"], date.today().isoformat())
        self.assertEqual(validate_payload(version, {}, user, partial=True), {})

    def test_slug_is_stable_and_ascii(self):
        self.assertEqual(slugify("Solicitacao de Revisao"), "solicitacao-de-revisao")

    def test_money_accepts_brazilian_input(self):
        field = SimpleNamespace(
            tipo="moeda",
            nome="Valor",
            validacao_json={},
            opcoes_json=[],
        )
        self.assertEqual(_normalize_field_value(field, "R$ 90.169,87"), "90169.87")

    def test_multiselect_removes_duplicates(self):
        field = SimpleNamespace(
            tipo="multiselect",
            nome="Servicos",
            validacao_json={},
            opcoes_json=["PARECER", "EVENTO"],
        )
        self.assertEqual(
            _normalize_field_value(field, ["PARECER", "EVENTO", "PARECER"]),
            ["PARECER", "EVENTO"],
        )

    def test_attachment_field_keeps_selected_file_names(self):
        field = SimpleNamespace(
            tipo="arquivo",
            nome="Documentos",
            validacao_json={"multiplo": True},
            opcoes_json=[],
        )
        self.assertEqual(
            _normalize_field_value(field, ["parecer.pdf", "memoria.xlsx"]),
            ["parecer.pdf", "memoria.xlsx"],
        )

    def test_definition_accepts_attachment_field(self):
        payload = FerramentaDefinitionInput.model_validate({
            "nome": "Solicitacao com anexo",
            "campos": [{
                "chave": "DOCUMENTOS",
                "nome": "Documentos",
                "tipo": "arquivo",
                "validacao": {"extensoes": ["pdf"], "max_mb": 10},
            }],
            "statuses": [{"codigo": "PENDENTE", "nome": "Pendente", "inicial": True}],
        })
        validate_definition(payload)

    def test_conditional_required_expression(self):
        condition = {"campo": "TIPO", "operador": "igual", "valor": "PARCELADO"}
        self.assertTrue(_condition_matches(condition, {"TIPO": "PARCELADO"}))
        self.assertTrue(_condition_matches(condition, {"TIPO": " parcelado "}))
        self.assertFalse(_condition_matches(condition, {"TIPO": "A_VISTA"}))

    def test_condition_accepts_any_configured_value(self):
        condition = {
            "campo": "TIPO_SOLICITACAO",
            "operador": "em",
            "valor": ["CONFECCAO DE MINUTA", "ANALISE DE PROPOSTA"],
        }
        self.assertTrue(_condition_matches(condition, {"TIPO_SOLICITACAO": "analise de proposta"}))
        self.assertTrue(_condition_matches(condition, {"TIPO_SOLICITACAO": "CONFECCAO DE MINUTA"}))
        self.assertFalse(_condition_matches(condition, {"TIPO_SOLICITACAO": "EVENTO"}))

    def test_condition_matches_multiselect_source(self):
        condition = {"campo": "SERVICOS", "operador": "em", "valor": ["PARECER", "EVENTO"]}
        self.assertTrue(_condition_matches(condition, {"SERVICOS": ["EVENTO", "REUNIAO"]}))
        self.assertFalse(_condition_matches(condition, {"SERVICOS": ["REUNIAO"]}))

    def test_numeric_condition_operators(self):
        self.assertTrue(_condition_matches({"campo": "VALOR", "operador": "maior_igual", "valor": "100"}, {"VALOR": "150"}))
        self.assertFalse(_condition_matches({"campo": "VALOR", "operador": "menor", "valor": "100"}, {"VALOR": "150"}))

    def test_calculated_percentage_field(self):
        calculated = SimpleNamespace(
            chave="HONORARIOS",
            validacao_json={"calculo": {"operacao": "percentual", "campo_base": "VALOR", "valor": 10}},
        )
        base = SimpleNamespace(chave="VALOR", validacao_json={})
        version = SimpleNamespace(campos=[base, calculated])
        self.assertEqual(_apply_calculated_fields(version, {"VALOR": "90169.87"})["HONORARIOS"], "9016.99")

    def test_definition_requires_exactly_one_initial_status(self):
        payload = FerramentaDefinitionInput.model_validate({
            "nome": "Solicitacoes",
            "campos": [{"chave": "CLIENTE", "nome": "Cliente"}],
            "statuses": [
                {"codigo": "PENDENTE", "nome": "Pendente"},
                {"codigo": "CONCLUIDO", "nome": "Concluido", "final": True},
            ],
        })
        with self.assertRaises(HTTPException) as context:
            validate_definition(payload)
        self.assertIn("status inicial", context.exception.detail)

    def test_transition_must_reference_existing_status(self):
        payload = FerramentaDefinitionInput.model_validate({
            "nome": "Solicitacoes",
            "campos": [{"chave": "CLIENTE", "nome": "Cliente"}],
            "statuses": [{"codigo": "PENDENTE", "nome": "Pendente", "inicial": True}],
            "transicoes": [{
                "origem_codigo": "PENDENTE",
                "destino_codigo": "INEXISTENTE",
                "nome": "Concluir",
            }],
        })
        with self.assertRaises(HTTPException) as context:
            validate_definition(payload)
        self.assertIn("inexistente", context.exception.detail.lower())

    def test_registration_can_disable_visible_status(self):
        payload = FerramentaDefinitionInput.model_validate({
            "nome": "Cadastro simples",
            "tipo": "CADASTRO",
            "configuracao": {"usar_status": False},
            "campos": [{"chave": "CLIENTE", "nome": "Cliente"}],
            "statuses": [],
        })
        validate_definition(payload)

    def test_request_always_requires_initial_status(self):
        payload = FerramentaDefinitionInput.model_validate({
            "nome": "Solicitacao simples",
            "tipo": "SOLICITACAO",
            "configuracao": {"usar_status": False},
            "campos": [{"chave": "CLIENTE", "nome": "Cliente"}],
            "statuses": [],
        })
        with self.assertRaises(HTTPException) as context:
            validate_definition(payload)
        self.assertIn("status inicial", context.exception.detail)


if __name__ == "__main__":
    unittest.main()
