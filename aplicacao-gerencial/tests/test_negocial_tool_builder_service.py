from __future__ import annotations

import unittest

from services.negocial_tool_builder_service import NegocialToolBuilderService


class NegocialToolBuilderServiceTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.service = NegocialToolBuilderService(negocial_service=None)

    def test_manager_sidebar_highlight_is_normalized(self) -> None:
        payload = {
            "nome": "Solicitacao destacada",
            "tipo": "CADASTRO",
            "destaque_gerencial": True,
            "configuracao": {"usar_status": False},
            "campos": [{"chave": "CLIENTE", "nome": "Cliente"}],
        }

        result = self.service._validate(payload)

        self.assertTrue(result["destaque_gerencial"])

    def test_approval_workflow_preserves_stages_actions_and_audiences(self) -> None:
        payload = {
            "nome": "Solicitacao operacional",
            "tipo": "SOLICITACAO",
            "configuracao": {"campo_titulo": "CLIENTE"},
            "campos": [{"chave": "CLIENTE", "nome": "Cliente", "obrigatorio": True}],
            "statuses": [
                {"codigo": "RECEBIDO", "nome": "Recebidos", "inicial": True},
                {"codigo": "EM_APROVACAO", "nome": "Em aprovacao"},
                {"codigo": "APROVADO", "nome": "Aprovados"},
                {"codigo": "REPROVADO", "nome": "Reprovados", "final": True},
            ],
            "transicoes": [
                {
                    "origem_codigo": "RECEBIDO",
                    "destino_codigo": "EM_APROVACAO",
                    "nome": "Enviar para aprovacao",
                    "permite_negociador": True,
                    "permite_gerencial": True,
                },
                {
                    "origem_codigo": "EM_APROVACAO",
                    "destino_codigo": "APROVADO",
                    "nome": "Aprovar",
                    "exige_justificativa": True,
                    "permite_gerencial": True,
                },
                {
                    "origem_codigo": "EM_APROVACAO",
                    "destino_codigo": "REPROVADO",
                    "nome": "Reprovar",
                    "exige_justificativa": True,
                    "permite_negociador": False,
                    "permite_gerencial": True,
                },
            ],
        }

        result = self.service._validate(payload)

        self.assertEqual([item["codigo"] for item in result["statuses"]], [
            "RECEBIDO", "EM_APROVACAO", "APROVADO", "REPROVADO",
        ])
        self.assertTrue(result["transicoes"][0]["permite_negociador"])
        self.assertTrue(result["transicoes"][1]["exige_justificativa"])
        self.assertFalse(result["transicoes"][2]["permite_negociador"])
        self.assertTrue(result["transicoes"][2]["permite_gerencial"])

    def test_screen_configuration_is_normalized_against_version_fields_and_statuses(self) -> None:
        payload = {
            "nome": "Parecer configuravel",
            "tipo": "SOLICITACAO",
            "configuracao": {
                "telas": [{
                    "id": "Aprovação",
                    "nome": "Aprovar parecer",
                    "tipo": "aprovacao",
                    "componentes": ["busca", "lista", "acoes", "inexistente"],
                    "status_codes": ["EM APROVACAO", "NAO_EXISTE"],
                    "historico_status_codes": ["APROVADO"],
                    "campos": ["CLIENTE", "CAMPO_INEXISTENTE"],
                    "visivel_negocial": False,
                    "layout": {
                        "colunas_desktop": 2,
                        "colunas_tablet": 2,
                        "colunas_mobile": 1,
                        "densidade": "confortavel",
                        "altura_uniforme": True,
                    },
                    "filtros": {
                        "mostrar_status": True,
                        "mostrar_negociador": False,
                        "mostrar_carteira": True,
                        "mostrar_ordenacao": False,
                        "campos": ["CLIENTE", "CAMPO_INEXISTENTE"],
                        "campo_data": "DATA_LIMITE",
                        "modo_data": "deadline",
                        "prazos_visiveis": ["all", "overdue", "today", "invalid", "today"],
                        "agrupar_prazo": True,
                        "iniciar_recolhido": True,
                    },
                    "campo_layout": {
                        "CLIENTE": {"papel": "titulo", "largura": "full", "copiavel": True},
                        "CAMPO_INEXISTENTE": {"papel": "destaque"},
                    },
                }],
            },
            "campos": [
                {"chave": "CLIENTE", "nome": "Cliente", "obrigatorio": True},
                {"chave": "DATA_LIMITE", "nome": "Data limite", "tipo": "data"},
            ],
            "statuses": [
                {"codigo": "EM_APROVACAO", "nome": "Em aprovacao", "inicial": True},
                {"codigo": "APROVADO", "nome": "Aprovado", "final": True},
            ],
            "transicoes": [{"origem_codigo": "EM_APROVACAO", "destino_codigo": "APROVADO"}],
        }

        result = self.service._validate(payload)
        screen = result["configuracao"]["telas"][0]

        self.assertEqual(screen["id"], "aprovacao")
        self.assertEqual(screen["componentes"], ["busca", "lista", "acoes"])
        self.assertEqual(screen["status_codes"], ["EM_APROVACAO"])
        self.assertEqual(screen["historico_status_codes"], ["APROVADO"])
        self.assertEqual(screen["campos"], ["CLIENTE"])
        self.assertFalse(screen["visivel_negocial"])
        self.assertTrue(screen["visivel_gerencial"])
        self.assertEqual(screen["layout"]["colunas_desktop"], 2)
        self.assertEqual(screen["layout"]["densidade"], "confortavel")
        self.assertTrue(screen["layout"]["altura_uniforme"])
        self.assertEqual(screen["filtros"]["campo_data"], "DATA_LIMITE")
        self.assertEqual(screen["filtros"]["modo_data"], "deadline")
        self.assertEqual(screen["filtros"]["prazos_visiveis"], ["all", "overdue", "today"])
        self.assertTrue(screen["filtros"]["agrupar_prazo"])
        self.assertEqual(screen["agrupamento"]["modo"], "deadline")
        self.assertTrue(screen["agrupamento"]["iniciar_recolhido"])
        self.assertTrue(screen["filtros"]["mostrar_status"])
        self.assertFalse(screen["filtros"]["mostrar_negociador"])
        self.assertTrue(screen["filtros"]["mostrar_carteira"])
        self.assertFalse(screen["filtros"]["mostrar_ordenacao"])
        self.assertEqual(screen["filtros"]["campos"], ["CLIENTE"])
        self.assertEqual(screen["campo_layout"]["CLIENTE"], {
            "papel": "titulo", "largura": "full", "copiavel": True,
        })
        self.assertNotIn("CAMPO_INEXISTENTE", screen["campo_layout"])

    def test_card_grouping_and_actions_are_normalized(self) -> None:
        payload = {
            "nome": "Fila por carteira",
            "tipo": "SOLICITACAO",
            "configuracao": {"telas": [{
                "id": "pendentes",
                "nome": "Pendentes",
                "tipo": "lista",
                "agrupamento": {"modo": "field", "campo": "CARTEIRA_CLIENTE", "iniciar_recolhido": True},
                "acoes_card": {
                    "copiar": True,
                    "copiar_campos": ["CLIENTE", "CONTRATO", "INVALIDO"],
                    "observacoes": True,
                    "mostrar_atualizacao": False,
                    "status_modo": "select",
                    "status_origem": "field",
                    "status_campo": "SITUACAO",
                    "botao_rotulo": "Concluir",
                    "botao_status": "CONCLUIDO",
                },
            }]},
            "campos": [
                {"chave": "CLIENTE", "nome": "Cliente"},
                {"chave": "CONTRATO", "nome": "Contrato"},
                {"chave": "CARTEIRA_CLIENTE", "nome": "Carteira"},
                {"chave": "SITUACAO", "nome": "Situacao", "tipo": "select", "opcoes": ["A VENCER", "VENCIDO"]},
            ],
            "statuses": [
                {"codigo": "PENDENTE", "nome": "Pendente", "inicial": True},
                {"codigo": "CONCLUIDO", "nome": "Concluido", "final": True},
            ],
        }

        screen = self.service._validate(payload)["configuracao"]["telas"][0]

        self.assertEqual(screen["agrupamento"], {
            "modo": "field", "campo": "CARTEIRA_CLIENTE", "iniciar_recolhido": True,
        })
        self.assertTrue(screen["acoes_card"]["copiar"])
        self.assertEqual(screen["acoes_card"]["copiar_campos"], ["CLIENTE", "CONTRATO"])
        self.assertTrue(screen["acoes_card"]["observacoes"])
        self.assertFalse(screen["acoes_card"]["mostrar_atualizacao"])
        self.assertEqual(screen["acoes_card"]["status_modo"], "select")
        self.assertEqual(screen["acoes_card"]["status_campo"], "SITUACAO")
        self.assertEqual(screen["acoes_card"]["botao_status"], "CONCLUIDO")

    def test_screen_layout_values_are_bounded_instead_of_discarded(self) -> None:
        payload = {
            "nome": "Cadastro simples",
            "tipo": "CADASTRO",
            "configuracao": {"usar_status": False, "telas": [{
                "id": "lista",
                "nome": "Lista",
                "tipo": "lista",
                "layout": {
                    "colunas_desktop": 99,
                    "colunas_tablet": 0,
                    "colunas_mobile": 8,
                    "densidade": "invalida",
                },
            }]},
            "campos": [{"chave": "CLIENTE", "nome": "Cliente"}],
        }

        screen = self.service._validate(payload)["configuracao"]["telas"][0]

        self.assertEqual(screen["layout"]["colunas_desktop"], 6)
        self.assertEqual(screen["layout"]["colunas_tablet"], 1)
        self.assertEqual(screen["layout"]["colunas_mobile"], 2)
        self.assertEqual(screen["layout"]["densidade"], "compacta")

    def test_dashboard_blocks_are_normalized_and_preserved(self) -> None:
        payload = {
            "nome": "Painel executivo",
            "tipo": "SOLICITACAO",
            "configuracao": {"telas": [{
                "id": "dashboard",
                "nome": "Dashboard",
                "tipo": "dashboard",
                "componentes": ["metricas"],
                "dashboard": {"columns": 99, "blocks": [
                    {
                        "id": "total-ho",
                        "tipo": "metric",
                        "titulo": "Honorarios recebidos",
                        "agregacao": "sum",
                        "campo": "HONORARIOS",
                        "status_codes": ["CONCLUIDO", "INVALIDO"],
                        "cor": "#10B981",
                        "largura": 4,
                        "limite": 50,
                    },
                    {
                        "id": "evolucao",
                        "tipo": "comparison",
                        "titulo": "Comparativo mensal",
                        "agregacao": "ratio",
                        "campo": "HONORARIOS",
                        "campo_secundario": "META",
                        "agrupador": "DATA",
                        "periodo": "month",
                        "condicao_campo": "HONORARIOS",
                        "condicao_operador": "gt",
                        "condicao_valor": "0",
                        "largura": 8,
                    },
                ]},
            }]},
            "campos": [
                {"chave": "HONORARIOS", "nome": "Honorarios", "tipo": "moeda"},
                {"chave": "DATA", "nome": "Data", "tipo": "data"},
                {"chave": "META", "nome": "Meta", "tipo": "moeda"},
            ],
            "statuses": [
                {"codigo": "PENDENTE", "nome": "Pendente", "inicial": True},
                {"codigo": "CONCLUIDO", "nome": "Concluido", "final": True},
            ],
        }

        dashboard = self.service._validate(payload)["configuracao"]["telas"][0]["dashboard"]

        self.assertEqual(dashboard["columns"], 12)
        self.assertEqual(len(dashboard["blocks"]), 2)
        self.assertEqual(dashboard["blocks"][0]["agregacao"], "sum")
        self.assertEqual(dashboard["blocks"][0]["campo"], "HONORARIOS")
        self.assertEqual(dashboard["blocks"][0]["status_codes"], ["CONCLUIDO"])
        self.assertEqual(dashboard["blocks"][0]["cor"], "#10b981")
        self.assertEqual(dashboard["blocks"][0]["limite"], 30)
        self.assertEqual(dashboard["blocks"][1]["periodo"], "month")
        self.assertEqual(dashboard["blocks"][1]["agrupador"], "DATA")
        self.assertEqual(dashboard["blocks"][1]["tipo"], "comparison")
        self.assertEqual(dashboard["blocks"][1]["agregacao"], "ratio")
        self.assertEqual(dashboard["blocks"][1]["campo_secundario"], "META")
        self.assertEqual(dashboard["blocks"][1]["condicao_operador"], "gt")
        self.assertEqual(dashboard["blocks"][1]["condicao_valor"], "0")

    def test_legacy_filter_component_keeps_previous_controls(self) -> None:
        payload = {
            "nome": "Ferramenta legada",
            "tipo": "CADASTRO",
            "configuracao": {"usar_status": False, "telas": [{
                "id": "lista",
                "nome": "Lista",
                "tipo": "lista",
                "componentes": ["filtros", "lista"],
                "filtros": {"modo_data": "none"},
            }]},
            "campos": [{"chave": "CLIENTE", "nome": "Cliente"}],
        }

        filters = self.service._validate(payload)["configuracao"]["telas"][0]["filtros"]

        self.assertTrue(filters["mostrar_status"])
        self.assertTrue(filters["mostrar_negociador"])
        self.assertTrue(filters["mostrar_ordenacao"])
        self.assertFalse(filters["mostrar_carteira"])

    def test_rules_calculation_and_transition_automations_are_normalized(self) -> None:
        payload = {
            "nome": "Calculo seguro",
            "tipo": "SOLICITACAO",
            "campos": [
                {"chave": "TIPO", "nome": "Tipo"},
                {"chave": "VALOR", "nome": "Valor", "tipo": "moeda"},
                {
                    "chave": "HONORARIOS", "nome": "Honorarios", "tipo": "moeda",
                    "condicao": {"campo": "TIPO", "operador": "igual", "valor": "ACORDO"},
                    "validacao": {"calculo": {"operacao": "percentual", "campo_base": "VALOR", "valor": 10}},
                },
                {"chave": "DATA_APROVACAO", "nome": "Data aprovacao", "tipo": "data"},
            ],
            "statuses": [
                {"codigo": "PENDENTE", "nome": "Pendente", "inicial": True},
                {"codigo": "APROVADO", "nome": "Aprovado", "final": True},
            ],
            "transicoes": [{
                "origem_codigo": "PENDENTE", "destino_codigo": "APROVADO", "nome": "Aprovar",
                "configuracao": {"automacoes": [{"tipo": "data_atual", "campo": "DATA_APROVACAO"}]},
            }],
        }
        result = self.service._validate(payload)
        honorarios = next(item for item in result["campos"] if item["chave"] == "HONORARIOS")
        self.assertTrue(honorarios["somente_leitura"])
        self.assertEqual(honorarios["validacao"]["calculo"]["campo_base"], "VALOR")
        self.assertEqual(result["transicoes"][0]["configuracao"]["automacoes"][0]["campo"], "DATA_APROVACAO")
        calculated = self.service._apply_calculations({"VALOR": "450,50"}, [
            {"chave": "VALOR", "validacao_json": {}},
            {"chave": "HONORARIOS", "validacao_json": honorarios["validacao"]},
        ])
        self.assertEqual(calculated["HONORARIOS"], "45.05")


if __name__ == "__main__":
    unittest.main()
