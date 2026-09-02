from __future__ import annotations

import threading
import time
import unittest
from datetime import datetime
from types import SimpleNamespace
from unittest.mock import Mock

import pandas as pd

from services.defasagem_domain import (
    attach_category_details,
    build_metrics,
    classify_defasagem,
    export_columns,
    filter_dataframe,
)
from services.defasagem_service import DefasagemService


class DefasagemServiceCacheTests(unittest.TestCase):
    def make_service(self) -> DefasagemService:
        service = DefasagemService.__new__(DefasagemService)
        service.settings = SimpleNamespace(cache_ttl_seconds=300)
        service._lock = threading.RLock()
        service._snapshot = None
        service._snapshot_history = {}
        service._expires_at = 0.0
        service._refreshing = False
        return service

    def test_fresh_snapshot_is_reused(self) -> None:
        service = self.make_service()
        snapshot = {"version": 1}
        service._snapshot = snapshot
        service._expires_at = time.monotonic() + 60
        service._build_snapshot = Mock()

        self.assertIs(service._load_snapshot(), snapshot)
        service._build_snapshot.assert_not_called()

    def test_expired_snapshot_returns_immediately_and_refreshes_in_background(self) -> None:
        service = self.make_service()
        stale = {"version": 1, "loaded_at": datetime(2026, 7, 21, 9, 0)}
        fresh = {"version": 2, "loaded_at": datetime(2026, 7, 21, 9, 5)}
        completed = threading.Event()
        service._snapshot = stale
        service._expires_at = time.monotonic() - 1

        def build() -> dict[str, int]:
            completed.set()
            return fresh

        service._build_snapshot = Mock(side_effect=build)

        self.assertIs(service._load_snapshot(), stale)
        self.assertTrue(completed.wait(timeout=1))
        for _ in range(100):
            if service._snapshot is fresh and not service._refreshing:
                break
            time.sleep(0.01)

        self.assertIs(service._snapshot, fresh)
        self.assertFalse(service._refreshing)
        service._build_snapshot.assert_called_once_with()

    def test_force_refresh_replaces_snapshot_synchronously(self) -> None:
        service = self.make_service()
        service._snapshot = {"version": 1, "loaded_at": datetime(2026, 7, 21, 9, 0)}
        fresh = {"version": 2, "loaded_at": datetime(2026, 7, 21, 9, 5)}
        service._build_snapshot = Mock(return_value=fresh)

        result = service._load_snapshot(force=True)

        self.assertEqual(result, fresh)
        self.assertIs(service._snapshot, result)

    def test_previous_snapshot_remains_available_for_report_version(self) -> None:
        service = self.make_service()
        first = {"loaded_at": datetime(2026, 7, 21, 10, 0), "version": 1}
        second = {"loaded_at": datetime(2026, 7, 21, 10, 5), "version": 2}

        service._store_snapshot(first)
        service._store_snapshot(second)

        self.assertIs(service._snapshot_by_version(first["loaded_at"].isoformat()), first)

    def test_report_uses_the_snapshot_version_shown_on_dashboard(self) -> None:
        service = self.make_service()
        first = {
            "loaded_at": datetime(2026, 7, 21, 10, 0),
            "data": pd.DataFrame([{"contrato": "CONTRATO-ANTERIOR"}]),
        }
        second = {
            "loaded_at": datetime(2026, 7, 21, 10, 5),
            "data": pd.DataFrame([{"contrato": "CONTRATO-NOVO"}]),
        }
        service._store_snapshot(first)
        service._store_snapshot(second)

        _, content = service.report(
            {},
            "csv",
            snapshot_version=first["loaded_at"].isoformat(),
        )
        report = content.decode("utf-8-sig")

        self.assertIn("CONTRATO-ANTERIOR", report)
        self.assertNotIn("CONTRATO-NOVO", report)


class DefasagemOperationalFilterTests(unittest.TestCase):
    def setUp(self) -> None:
        self.data = pd.DataFrame(
            [
                {
                    "contrato": "1",
                    "operador": "ANA",
                    "data_ultimo_acionamento": pd.Timestamp("2026-01-10"),
                    "sem_retorno": True,
                    "is_critico": True,
                    "is_negociacao": True,
                    "is_possivel_negocio": False,
                    "is_desinteresse": False,
                    "negociacao_sem_retorno": True,
                    "possivel_negocio_sem_retorno": False,
                    "desinteresse_sem_retorno": False,
                },
                {
                    "contrato": "2",
                    "operador": "BRUNO",
                    "data_ultimo_acionamento": pd.NaT,
                    "sem_retorno": True,
                    "is_critico": True,
                    "is_negociacao": False,
                    "is_possivel_negocio": True,
                    "is_desinteresse": False,
                    "negociacao_sem_retorno": False,
                    "possivel_negocio_sem_retorno": True,
                    "desinteresse_sem_retorno": False,
                },
                {
                    "contrato": "3",
                    "operador": "ANA",
                    "data_ultimo_acionamento": pd.Timestamp("2026-07-20"),
                    "sem_retorno": False,
                    "is_critico": False,
                    "is_negociacao": False,
                    "is_possivel_negocio": False,
                    "is_desinteresse": True,
                    "negociacao_sem_retorno": False,
                    "possivel_negocio_sem_retorno": False,
                    "desinteresse_sem_retorno": False,
                },
            ]
        )

    def test_operational_filter_selects_only_requested_situation(self) -> None:
        result = filter_dataframe(
            self.data,
            {"filtro_operacional": "negociacao_sem_retorno"},
        )

        self.assertEqual(result["contrato"].tolist(), ["1"])

    def test_clients_without_action_use_null_action_date(self) -> None:
        result = filter_dataframe(
            self.data,
            {"filtro_operacional": "cliente_sem_acionamento"},
        )

        self.assertEqual(result["contrato"].tolist(), ["2"])

    def test_operator_filter_requires_operator_and_missing_response(self) -> None:
        result = filter_dataframe(
            self.data,
            {"operador_sem_retorno": "ANA"},
        )

        self.assertEqual(result["contrato"].tolist(), ["1"])

    def test_defasagem_type_can_be_combined_with_operational_filter(self) -> None:
        result = filter_dataframe(
            self.data,
            {
                "tipo_defasagem": "possivel_negocio",
                "filtro_operacional": "clientes_criticos",
            },
        )

        self.assertEqual(result["contrato"].tolist(), ["2"])


class DefasagemDashboardTests(unittest.TestCase):
    def test_metrics_use_official_last_action_defasagem(self) -> None:
        official_days = pd.Series([30, 120, 300, 500, pd.NA], dtype="Int64")
        data = pd.DataFrame({
            "contrato_key": ["1", "2", "3", "4", "5"],
            "faixa_defasagem": classify_defasagem(official_days),
            "faixa_defasagem_cards": classify_defasagem(pd.Series([1, 1, 1, 1, 1], dtype="Int64")),
            "data_ultimo_acionamento": [pd.Timestamp("2026-01-01")] * 4 + [pd.NaT],
        })

        metrics = build_metrics(data)

        self.assertEqual(metrics["faixa_ate_3_meses"], 1)
        self.assertEqual(metrics["faixa_ate_6_meses"], 1)
        self.assertEqual(metrics["faixa_ate_1_ano"], 1)
        self.assertEqual(metrics["faixa_apos_1_ano"], 1)
        self.assertEqual(metrics["sem_acionamento"], 1)

        visual_metrics = build_metrics(data, use_card_defasagem=True)
        self.assertEqual(visual_metrics["faixa_ate_3_meses"], 5)
        self.assertEqual(visual_metrics["faixa_apos_1_ano"], 0)

    def test_priority_queue_follows_operational_order(self) -> None:
        data = pd.DataFrame(
            [
                {
                    "contrato_key": "SEM-HISTORICO",
                    "cliente": "Cliente sem historico",
                    "nome_op": "CARLA",
                    "operador": "Sem operador",
                    "is_critico": True,
                    "negociacao_sem_retorno": False,
                    "possivel_negocio_sem_retorno": False,
                    "desinteresse_sem_retorno": False,
                    "data_ultimo_acionamento": pd.NaT,
                    "dias_sem_acionamento": pd.NA,
                    "faixa_defasagem": "Sem acionamento",
                    "situacao_especial": "Demais",
                },
                {
                    "contrato_key": "NEGOCIACAO",
                    "cliente": "Cliente negociando",
                    "nome_op": "ANA",
                    "operador": "OPERADOR 1",
                    "is_critico": True,
                    "negociacao_sem_retorno": True,
                    "possivel_negocio_sem_retorno": False,
                    "desinteresse_sem_retorno": False,
                    "data_ultimo_acionamento": pd.Timestamp("2026-01-01"),
                    "dias_sem_acionamento": 200,
                    "faixa_defasagem": "Ate 1 ano",
                    "situacao_especial": "Negociacao",
                },
                {
                    "contrato_key": "POSSIVEL",
                    "cliente": "Cliente possivel",
                    "nome_op": "BRUNO",
                    "operador": "OPERADOR 2",
                    "is_critico": True,
                    "negociacao_sem_retorno": False,
                    "possivel_negocio_sem_retorno": True,
                    "desinteresse_sem_retorno": False,
                    "data_ultimo_acionamento": pd.Timestamp("2025-01-01"),
                    "dias_sem_acionamento": 500,
                    "faixa_defasagem": "Apos 1 ano",
                    "situacao_especial": "Possivel negocio",
                },
            ]
        )
        service = DefasagemService.__new__(DefasagemService)
        snapshot = {
            "data": data,
            "guarantees": pd.DataFrame(),
            "triggers": pd.DataFrame(),
            "timeline": pd.DataFrame(),
            "operator_activity": pd.DataFrame(),
            "loaded_at": datetime(2026, 7, 21, 12, 0),
            "contracts": 3,
            "actions": 2,
        }
        service._filtered = Mock(return_value=(snapshot, data))
        service.settings = SimpleNamespace(cache_ttl_seconds=300)

        payload = service.dashboard({})

        self.assertEqual(
            [item["cliente"] for item in payload["priority_clients"]],
            ["Cliente sem historico", "Cliente negociando", "Cliente possivel"],
        )
        self.assertEqual(
            [item["prioridade_fila"] for item in payload["priority_clients"]],
            ["Sem acionamentos", "Negociacao s/ retorno", "Possivel negocio s/ retorno"],
        )
        self.assertEqual(payload["metrics"]["clientes_criticos"], 3)

    def test_operator_portfolio_alerts_separate_wallets(self) -> None:
        data = pd.DataFrame([
            {"nome_op": "ANA", "carteira": "GAMMA", "negociacao_sem_retorno": True, "possivel_negocio_sem_retorno": False},
            {"nome_op": "ANA", "carteira": "ALPHA", "negociacao_sem_retorno": False, "possivel_negocio_sem_retorno": True},
            {"nome_op": "BRUNO", "carteira": "GAMMA", "negociacao_sem_retorno": False, "possivel_negocio_sem_retorno": False},
        ])

        result = DefasagemService._operator_portfolio_alerts(data)

        self.assertEqual(len(result), 2)
        self.assertEqual({(item["nome_op"], item["carteira"]) for item in result}, {("ANA", "GAMMA"), ("ANA", "ALPHA")})
        self.assertTrue(all(item["total"] == item["negociacao_sem_retorno"] + item["possivel_negocio_sem_retorno"] for item in result))


class DefasagemCategoryTests(unittest.TestCase):
    def test_categories_are_attached_by_contract_and_client_without_duplicate_rows(self) -> None:
        contracts = pd.DataFrame([
            {"contrato_key": "1", "cliente_key": "CLIENTE A"},
            {"contrato_key": "2", "cliente_key": "CLIENTE B"},
        ])
        guarantees = pd.DataFrame([
            {"contrato_key": "1", "cliente_key": "", "tipo_garantia": "IMOVEL"},
            {"contrato_key": "", "cliente_key": "CLIENTE B", "tipo_garantia": "VEICULO"},
        ])
        triggers = pd.DataFrame([
            {"contrato_key": "1", "cliente_key": "", "gatilho": "CITACAO"},
            {"contrato_key": "1", "cliente_key": "", "gatilho": "PENHORA"},
        ])

        result = attach_category_details(contracts, guarantees, triggers)

        self.assertEqual(len(result), 2)
        self.assertEqual(result.loc[0, "garantias"], "IMOVEL")
        self.assertEqual(result.loc[1, "garantias"], "VEICULO")
        self.assertEqual(result.loc[0, "gatilhos"], "CITACAO | PENHORA")
        self.assertEqual(result.loc[0, "quantidade_gatilhos"], 2)
        self.assertTrue(bool(result.loc[1, "tem_garantia"]))

    def test_linked_analysis_separates_occurrences_from_clients(self) -> None:
        data = pd.DataFrame([
            {
                "contrato_key": "1", "tem_gatilho": True, "tem_garantia": True,
                "quantidade_gatilhos": 2, "quantidade_garantias": 3,
                "_prioridade_ordem": 0, "dias_sem_acionamento": pd.NA,
            },
            {
                "contrato_key": "2", "tem_gatilho": False, "tem_garantia": True,
                "quantidade_gatilhos": 0, "quantidade_garantias": 1,
                "_prioridade_ordem": 7, "dias_sem_acionamento": 10,
            },
        ])

        analysis = DefasagemService._linked_analysis(data)

        self.assertEqual(analysis["total"], 2)
        self.assertEqual(analysis["metrics"]["com_gatilho"], 1)
        self.assertEqual(analysis["metrics"]["com_garantia"], 2)
        self.assertEqual(analysis["metrics"]["gatilhos_total"], 2)
        self.assertEqual(analysis["metrics"]["garantias_total"], 4)

    def test_general_report_columns_include_triggers_and_guarantees(self) -> None:
        data = pd.DataFrame([{
            "contrato": "1",
            "cliente": "Cliente A",
            "gatilhos": "CITACAO",
            "quantidade_gatilhos": 1,
            "garantias": "IMOVEL",
            "quantidade_garantias": 1,
            "ultimo_acionamento_cards": "DISCADOR",
            "faixa_defasagem_cards": "Ate 3 meses",
        }])

        exported = export_columns(data)

        self.assertEqual(
            exported.columns.tolist(),
            ["contrato", "cliente", "gatilhos", "quantidade_gatilhos", "garantias", "quantidade_garantias"],
        )

if __name__ == "__main__":
    unittest.main()
