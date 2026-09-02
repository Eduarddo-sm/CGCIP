from __future__ import annotations

import unittest
from types import SimpleNamespace
from urllib.parse import urlparse

from backend.routes import dispatch_get, dispatch_post


class FakeHandler:
    def __init__(self) -> None:
        self.responses: list[object] = []
        self.errors: list[tuple[str, int]] = []
        self.payload: dict = {}

    def json_response(self, payload, *_args, **_kwargs) -> None:
        self.responses.append(payload)

    def error_response(self, message: str, status: int) -> None:
        self.errors.append((message, status))

    def csv_response(self, filename: str, content: bytes) -> None:
        self.responses.append({"filename": filename, "content": content})

    def read_json(self) -> dict:
        return self.payload

    def handle_protocolo(self, action) -> None:
        self.json_response(action())

    def handle_parecer(self, action) -> None:
        self.json_response(action())

    def handle_colchao(self, action) -> None:
        self.json_response(action())

    def require_permission(self, _permission: str):
        return {"id": 1, "role": "admin"}

    def require_admin(self):
        return {"id": 1, "role": "admin"}

    def _mark_parecer_and_notification(self, pk: str, username: str) -> dict:
        return {"pk": pk, "username": username}

    def _int_query(self, query, key: str, default: int) -> int:
        return int(query.get(key, [str(default)])[0] or default)


class RouteDispatcherTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.handler = FakeHandler()
        self.user = {"id": 1, "username": "gestor", "role": "admin"}
        self.state = SimpleNamespace(
            production_analytics=SimpleNamespace(
                dashboard=lambda filters: {"filters": filters, "agreements": 3},
                negotiator_details=lambda filters: {"filters": filters, "agreements": [{"client": "Cliente"}]},
                status_details=lambda filters: {"filters": filters, "agreements": [{"client": "Cliente pago"}]},
                dimension_details=lambda filters: {"filters": filters, "agreements": [{"client": "Cliente SP"}]},
                day_details=lambda filters: {"filters": filters, "agreements": [{"client": "Cliente do dia"}]},
            ),
            main_hub=SimpleNamespace(payload=lambda username, version: {"username": username, "version": version}),
            protocolo=SimpleNamespace(
                records=lambda: [{"id": 7}],
                pending_records=lambda limit=None: [{"limit": limit}],
                dashboard=lambda: {"total": 1},
                get_config=lambda: {"sheet": "Sol. Protocolo"},
                create=lambda payload, username: {"payload": payload, "username": username},
                update_status=lambda row, status, username: {"row": row, "status": status, "username": username},
                update_cell=lambda row, header, value, username: {
                    "row": row, "header": header, "value": value, "username": username,
                },
            ),
            parecer=SimpleNamespace(
                read_records=lambda: [{"pk": "1"}],
                read_pendentes=lambda: [],
                read_aprovacao_pendente=lambda: [],
                read_aprovacao_historico=lambda: [],
                dashboard=lambda: {"total": 1},
                relatorio_csv=lambda: ("pareceres.csv", b"PK;CLIENTE\n1;Cliente"),
                history=lambda: [],
                get_config=lambda: {},
            ),
        )

    def test_protocol_route_is_dispatched_by_domain(self) -> None:
        handled = dispatch_get(self.handler, self.state, urlparse("/api/protocolo/pendentes?limit=25"), self.user)

        self.assertTrue(handled)
        self.assertEqual(self.handler.responses, [[{"limit": 25}]])

    def test_main_hub_route_passes_client_version(self) -> None:
        handled = dispatch_get(self.handler, self.state, urlparse("/api/main-hub?version=v12"), self.user)

        self.assertTrue(handled)
        self.assertEqual(self.handler.responses, [{"username": "gestor", "version": "v12"}])

    def test_parecer_route_is_dispatched_by_domain(self) -> None:
        handled = dispatch_get(self.handler, self.state, urlparse("/api/pareceres"), self.user)

        self.assertTrue(handled)
        self.assertEqual(self.handler.responses, [[{"pk": "1"}]])

    def test_parecer_report_returns_downloadable_csv(self) -> None:
        handled = dispatch_get(
            self.handler,
            self.state,
            urlparse("/api/pareceres/relatorio.csv"),
            self.user,
        )

        self.assertTrue(handled)
        self.assertEqual(self.handler.responses[0]["filename"], "pareceres.csv")
        self.assertIn(b"Cliente", self.handler.responses[0]["content"])

    def test_unknown_route_remains_available_to_the_main_handler(self) -> None:
        handled = dispatch_get(self.handler, self.state, urlparse("/api/negociadores/10/events"), self.user)

        self.assertFalse(handled)
        self.assertEqual(self.handler.responses, [])

    def test_production_analytics_route_is_dispatched(self) -> None:
        handled = dispatch_get(
            self.handler,
            self.state,
            urlparse("/api/analise/producao?carteira=GAMMA&mes=7&ano=2026"),
            self.user,
        )

        self.assertTrue(handled)
        self.assertEqual(self.handler.responses[0]["agreements"], 3)
        self.assertEqual(self.handler.responses[0]["filters"]["wallet"], "GAMMA")

    def test_production_analytics_negotiator_details_route_is_dispatched(self) -> None:
        handled = dispatch_get(
            self.handler,
            self.state,
            urlparse("/api/analise/producao/negociador?carteira=GAMMA&mes=7&ano=2026&negociador=usuario.demo"),
            self.user,
        )

        self.assertTrue(handled)
        self.assertEqual(self.handler.responses[0]["filters"]["negotiator"], "usuario.demo")
        self.assertEqual(self.handler.responses[0]["agreements"][0]["client"], "Cliente")

    def test_production_analytics_status_details_route_is_dispatched(self) -> None:
        handled = dispatch_get(
            self.handler,
            self.state,
            urlparse("/api/analise/producao/status?mes=7&ano=2026&status=PAGAMENTO_REALIZADO"),
            self.user,
        )

        self.assertTrue(handled)
        self.assertEqual(self.handler.responses[0]["filters"]["status"], "PAGAMENTO_REALIZADO")
        self.assertEqual(self.handler.responses[0]["agreements"][0]["client"], "Cliente pago")

    def test_production_analytics_dimension_details_route_is_dispatched(self) -> None:
        handled = dispatch_get(
            self.handler,
            self.state,
            urlparse("/api/analise/producao/dimensao?carteira=GAMMA&mes=7&ano=2026&dimensao=uf&valor_dimensao=SP"),
            self.user,
        )

        self.assertTrue(handled)
        self.assertEqual(self.handler.responses[0]["filters"]["dimension"], "uf")
        self.assertEqual(self.handler.responses[0]["filters"]["dimension_value"], "SP")
        self.assertEqual(self.handler.responses[0]["agreements"][0]["client"], "Cliente SP")

    def test_production_analytics_day_details_route_is_dispatched(self) -> None:
        handled = dispatch_get(
            self.handler,
            self.state,
            urlparse("/api/analise/producao/dia?carteira=GAMMA&mes=7&ano=2026&data=2026-07-17&metrica=paid_value"),
            self.user,
        )

        self.assertTrue(handled)
        self.assertEqual(self.handler.responses[0]["filters"]["selected_date"], "2026-07-17")
        self.assertEqual(self.handler.responses[0]["filters"]["metric"], "paid_value")
        self.assertEqual(self.handler.responses[0]["agreements"][0]["client"], "Cliente do dia")

    def test_protocol_post_preserves_payload_and_user(self) -> None:
        self.handler.payload = {"row": 17, "status": "CONCLUIDO"}

        handled = dispatch_post(self.handler, self.state, "/api/protocolo/status", self.user)

        self.assertTrue(handled)
        self.assertEqual(
            self.handler.responses,
            [{"row": 17, "status": "CONCLUIDO", "username": "gestor"}],
        )

    def test_parecer_post_preserves_pk_and_user(self) -> None:
        self.handler.payload = {"pk": "NPJ-42"}

        handled = dispatch_post(self.handler, self.state, "/api/pareceres/marcar-solicitado", self.user)

        self.assertTrue(handled)
        self.assertEqual(self.handler.responses, [{"pk": "NPJ-42", "username": "gestor"}])


if __name__ == "__main__":
    unittest.main()
