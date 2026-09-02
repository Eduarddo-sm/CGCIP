import unittest

from services.parecer_service import ParecerService
from services.negocial_parecer_mixin import NegocialParecerMixin
from services.negocial_service import NegocialService


class ParecerDashboardTestCase(unittest.TestCase):
    def test_dashboard_separates_approval_request_and_rejection_stages(self):
        service = ParecerService.__new__(ParecerService)
        service.read_records = lambda: [
            {"SOLICITADO?": "NAO", "OPERADOR": "Excel", "DATA": "2026-07-01"},
            {"SOLICITADO?": "SIM", "OPERADOR": "Excel", "DATA": "2026-07-02"},
            {"__source": "sistema", "STATUS": "PENDENTE", "APROVACAO": "PENDENTE", "OPERADOR": "Ana", "DATA": "2026-07-03"},
            {"__source": "sistema", "STATUS": "PENDENTE", "APROVACAO": "APROVADO", "OPERADOR": "Bia", "DATA": "2026-07-04"},
            {"__source": "sistema", "STATUS": "SOLICITADO", "APROVACAO": "APROVADO", "OPERADOR": "Caio", "DATA": "2026-07-05"},
            {"__source": "sistema", "STATUS": "CANCELADO", "APROVACAO": "REPROVADO", "OPERADOR": "Davi", "DATA": "2026-07-06"},
        ]
        service.get_config = lambda: {"solicitado_column": "SOLICITADO?"}

        dashboard = service.dashboard()

        self.assertEqual(dashboard["total"], 6)
        self.assertEqual(dashboard["aguardando_aprovacao"], 1)
        self.assertEqual(dashboard["pendentes"], 2)
        self.assertEqual(dashboard["solicitados"], 2)
        self.assertEqual(dashboard["aprovados"], 2)
        self.assertEqual(dashboard["reprovados"], 1)
        self.assertEqual(len(dashboard["fila_atencao"]), 3)
        self.assertEqual(dashboard["fila_atencao"][0]["target"], "aprovacao")

    def test_approval_history_contains_approved_and_rejected_decisions(self):
        service = NegocialParecerMixin()
        service.read_parecer_records = lambda: [
            {"__source": "sistema", "APROVACAO": "PENDENTE"},
            {"__source": "sistema", "APROVACAO": "APROVADO"},
            {"__source": "sistema", "APROVACAO": "REPROVADO"},
            {"__source": "excel", "APROVACAO": "APROVADO"},
        ]

        history = service.read_parecer_approval_history()

        self.assertEqual([row["APROVACAO"] for row in history], ["APROVADO", "REPROVADO"])

    def test_parecer_mapping_exposes_request_and_decision_dates(self):
        service = NegocialService.__new__(NegocialService)
        row = {
            "id": 12,
            "status": "SOLICITADO",
            "approval_status": "APROVADO",
            "approval_reason": "Validado pela gerencia",
            "created_at": "2026-07-16 09:00:00",
            "updated_at": "2026-07-16 10:30:00",
            "requested_at": "2026-07-16 10:20:00",
            "approval_decided_at": "2026-07-16 10:10:00",
            "data_solicitacao": "2026-07-16",
            "npj": "20260000000001",
            "cliente": "Cliente teste",
            "motivo": "PARECER",
            "descricao": "Descricao",
            "operador": "negociador.teste",
            "carteira": "GAMMA",
        }

        mapped = service._map_parecer_row(row, 1)

        self.assertEqual(mapped["DATA SOLICITADO"], "2026-07-16 10:20:00")
        self.assertEqual(mapped["DATA APROVADO/REPROVADO"], "2026-07-16 10:10:00")


if __name__ == "__main__":
    unittest.main()
