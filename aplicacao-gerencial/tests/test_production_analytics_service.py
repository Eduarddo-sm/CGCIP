from __future__ import annotations

import unittest
from datetime import date, datetime, timedelta
from types import SimpleNamespace

from services.production_analytics_service import ProductionAnalyticsService


class ProductionAnalyticsServiceTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.service = ProductionAnalyticsService(SimpleNamespace(database_backend="postgresql"))

    def row(self, **overrides):
        base = {
            "id": 1,
            "data_acordo": date(2026, 7, 10),
            "data_pagamento": date(2026, 7, 10),
            "cliente": "Cliente",
            "identifier": "NPJ1",
            "valor_total_acordo": 1000,
            "valor_entrada": 0,
            "tipo_acordo": "A_VISTA",
            "data_vencimento": date.today() + timedelta(days=3),
            "status": "PAGAMENTO_REALIZADO",
            "carteira": "GAMMA",
            "username": "negociador",
            "meta_pagamento": 1000,
            "gamma_valor_ho": 100,
            "dynamic_honorarios": 0,
            "usa_percentual_ho": True,
            "percentual_ho_padrao": 10,
            "gecor": "4962",
            "uf": "SP",
            "updated_at": datetime.now(),
        }
        base.update(overrides)
        return base

    def test_summary_uses_paid_honorarios_and_goal(self) -> None:
        rows = [self.row(), self.row(id=2, status="AGUARDANDO_PAGAMENTO", gamma_valor_ho=80)]

        summary = self.service._summary(rows, {"month": 7, "year": 2026})

        self.assertEqual(summary["agreements"], 2)
        self.assertEqual(summary["paid_honorarios"], 100)
        self.assertEqual(summary["projected_honorarios"], 180)
        self.assertEqual(summary["goal"], 1000)
        self.assertEqual(summary["goal_percent"], 10)

    def test_conversion_only_compares_payments_and_breaks(self) -> None:
        rows = [
            self.row(id=1, status="PAGAMENTO_REALIZADO"),
            self.row(id=2, status="PAGAMENTO_REALIZADO"),
            self.row(id=3, status="QUEBRA"),
            self.row(id=4, status="PROPOSTA"),
            self.row(id=5, status="PROPOSTA_NEGADA"),
            self.row(id=6, status="AGUARDANDO_PAGAMENTO"),
        ]

        self.assertEqual(self.service._conversion_rate(rows), 66.67)
        self.assertEqual(
            self.service._summary(rows, {"month": 7, "year": 2026})["conversion_rate"],
            66.67,
        )
        self.assertEqual(self.service._negotiators(rows)[0]["conversion_rate"], 66.67)

    def test_pipeline_separates_overdue_due_soon_and_stagnant(self) -> None:
        rows = [
            self.row(status="PROPOSTA", data_vencimento=date.today() - timedelta(days=2), updated_at=datetime.now()),
            self.row(id=2, status="AGUARDANDO_PAGAMENTO", data_vencimento=date.today() + timedelta(days=2), updated_at=datetime.now() - timedelta(days=8)),
        ]

        pipeline = self.service._pipeline(rows)

        self.assertEqual(pipeline["counts"]["overdue"], 1)
        self.assertEqual(pipeline["counts"]["due_soon"], 1)
        self.assertEqual(pipeline["counts"]["stagnant"], 1)

    def test_dynamic_wallet_honorarios_use_configured_percentage(self) -> None:
        row = self.row(carteira="CAIXA", gamma_valor_ho=0, dynamic_honorarios=None, valor_total_acordo=2500, percentual_ho_padrao=8)
        self.assertEqual(self.service._honorarios(row), 200)

    def test_dynamic_zero_honorarios_does_not_fall_back_to_percentage(self) -> None:
        row = self.row(
            carteira="ALPHA",
            gamma_valor_ho=0,
            dynamic_honorarios=0,
            valor_total_acordo=2500,
            percentual_ho_padrao=10,
        )

        self.assertEqual(self.service._honorarios(row), 0)

    def test_alpha_uses_materialized_exceptional_honorarios(self) -> None:
        row = self.row(
            carteira="ALPHA",
            gamma_valor_ho=0,
            dynamic_honorarios=275.43,
            valor_total_acordo=2500,
            percentual_ho_padrao=8,
        )

        self.assertIn("HONORARIOS_CALCULADOS", self.service.DYNAMIC_HO_KEYS)
        self.assertEqual(self.service._honorarios(row), 275.43)

    def test_gamma_zero_honorarios_does_not_fall_back_to_ten_percent(self) -> None:
        row = self.row(gamma_valor_ho=0, valor_total_acordo=2500, percentual_ho_padrao=10)
        self.assertEqual(self.service._honorarios(row), 0)

    def test_negotiator_agreements_sort_by_value_and_show_stored_honorarios(self) -> None:
        rows = [
            self.row(id=1, cliente="Menor pago", valor_total_acordo=1000, gamma_valor_ho=100),
            self.row(
                id=2,
                cliente="Maior em aberto",
                identifier="20230231004000",
                valor_total_acordo=5000,
                gamma_valor_ho=500,
                status="PROPOSTA",
            ),
            self.row(id=3, cliente="Intermediario pago", valor_total_acordo=3000, gamma_valor_ho=300),
        ]

        agreements = self.service._negotiator_agreements(rows)

        self.assertEqual([item["client"] for item in agreements], ["Maior em aberto", "Intermediario pago", "Menor pago"])
        self.assertEqual(agreements[0]["received_honorarios"], 500)
        self.assertEqual(agreements[1]["received_honorarios"], 300)
        self.assertEqual(agreements[0]["identifier"], "20230231004000")
        self.assertEqual(agreements[0]["status"], "PROPOSTA")
        self.assertEqual(agreements[0]["status_label"], "Proposta")

    def test_journey_filter_is_normalized_without_losing_selected_dimensions(self) -> None:
        filters = self.service._normalize_filters({
            "period_scope": "journey",
            "wallet": "gamma",
            "negotiator": "negociador",
        })

        self.assertEqual(filters["period_scope"], "journey")
        self.assertEqual(filters["wallet"], "GAMMA")
        self.assertEqual(filters["negotiator"], "negociador")

    def test_year_filter_uses_full_calendar_year(self) -> None:
        filters = self.service._normalize_filters({"period_scope": "year", "year": 2025})

        self.assertEqual(filters["period_scope"], "year")
        self.assertEqual(
            self.service._selected_period_bounds(filters),
            (date(2025, 1, 1), date(2026, 1, 1)),
        )

    def test_year_trend_fills_all_twelve_months(self) -> None:
        rows = [
            self.row(
                competencia=date(2025, 3, 1),
                data_acordo=date(2025, 3, 10),
                gamma_valor_ho=125,
            ),
        ]

        trend = self.service._trend(rows, {"period_scope": "year", "year": 2025})

        self.assertEqual(len(trend), 12)
        self.assertEqual(trend[2]["paid_honorarios"], 125)
        self.assertEqual(trend[11]["cumulative_honorarios"], 125)

    def test_comparisons_align_years_and_months(self) -> None:
        rows = [
            self.row(
                competencia=date(2025, 7, 1),
                data_acordo=date(2025, 7, 10),
                valor_total_acordo=1000,
                gamma_valor_ho=100,
            ),
            self.row(
                id=2,
                competencia=date(2026, 7, 1),
                data_acordo=date(2026, 7, 10),
                valor_total_acordo=2500,
                gamma_valor_ho=250,
            ),
        ]

        comparisons = self.service._comparisons(rows, 2026)

        self.assertEqual(comparisons["annual"][0]["total_value"], 1000)
        self.assertEqual(comparisons["annual"][1]["total_value"], 2500)
        self.assertEqual(comparisons["monthly"][6]["previous"]["paid_honorarios"], 100)
        self.assertEqual(comparisons["monthly"][6]["current"]["paid_honorarios"], 250)
        self.assertEqual(comparisons["monthly"][6]["current"]["paid_count"], 1)
        self.assertEqual(comparisons["monthly"][6]["current"]["breaks_count"], 0)
        self.assertEqual(comparisons["years"], [2025, 2026])
        self.assertEqual(comparisons["monthly"][6]["years"]["2025"]["total_value"], 1000)
        self.assertEqual(comparisons["monthly"][6]["years"]["2026"]["total_value"], 2500)

    def test_journey_trend_fills_months_without_production(self) -> None:
        current = date.today()
        first_year, first_month = (current.year - 1, 12) if current.month == 1 else (current.year, current.month - 1)
        rows = [
            self.row(
                competencia=date(first_year, first_month, 1),
                data_acordo=date(first_year, first_month, 10),
                gamma_valor_ho=100,
            ),
            self.row(
                id=2,
                competencia=date(current.year, current.month, 1),
                data_acordo=current,
                gamma_valor_ho=200,
            ),
        ]

        trend = self.service._trend(rows, {"period_scope": "journey"})

        self.assertEqual(len(trend), 2)
        self.assertEqual(trend[0]["paid_honorarios"], 100)
        self.assertEqual(trend[1]["paid_honorarios"], 200)
        self.assertEqual(trend[1]["cumulative_honorarios"], 300)

    def test_executive_trend_exposes_all_interactive_metrics(self) -> None:
        rows = [
            self.row(id=1, valor_total_acordo=1000, status="PAGAMENTO_REALIZADO", tipo_acordo="A_VISTA", gamma_valor_ho=100),
            self.row(id=2, valor_total_acordo=2000, status="QUEBRA", tipo_acordo="PARCELADO", gamma_valor_ho=200),
            self.row(id=3, valor_total_acordo=3000, status="PROPOSTA_NEGADA", tipo_acordo="PARCELADO", gamma_valor_ho=300),
        ]

        trend = self.service._daily(rows)[0]

        self.assertEqual(trend["total_value"], 6000)
        self.assertEqual(trend["paid_value"], 1000)
        self.assertEqual(trend["paid_honorarios"], 100)
        self.assertEqual(trend["cash_value"], 1000)
        self.assertEqual(trend["installment_total"], 5000)
        self.assertEqual(trend["breaks_value"], 2000)
        self.assertEqual(trend["negated_value"], 3000)

    def test_daily_paid_metrics_use_payment_date(self) -> None:
        rows = [
            self.row(
                data_acordo=date(2026, 8, 17),
                data_pagamento=date(2026, 8, 26),
                valor_total_acordo=70000,
                gamma_valor_ho=7000,
            ),
        ]

        trend = {item["date"]: item for item in self.service._daily(rows)}

        self.assertEqual(trend["2026-08-17"]["total_value"], 70000)
        self.assertEqual(trend["2026-08-17"]["paid_honorarios"], 0)
        self.assertEqual(trend["2026-08-26"]["paid_honorarios"], 7000)
        self.assertEqual(trend["2026-08-26"]["paid_value"], 70000)
        self.assertEqual(trend["2026-08-26"]["paid"], 1)

    def test_payment_metric_reference_falls_back_to_agreement_date(self) -> None:
        row = self.row(data_acordo=date(2026, 8, 17), data_pagamento=None)

        self.assertEqual(
            self.service._metric_reference_date(row, "paid_honorarios"),
            date(2026, 8, 17),
        )

    def test_journey_period_uses_first_available_competence(self) -> None:
        rows = [
            self.row(competencia=date(2024, 6, 1)),
            self.row(id=2, competencia=date(2025, 2, 1)),
        ]

        period = self.service._period_metadata({"period_scope": "journey"}, rows)

        self.assertEqual(period["scope"], "journey")
        self.assertEqual(period["start"], "2024-06-01")
        self.assertEqual(period["granularity"], "month")

    def test_gamma_wallet_analysis_keeps_total_entry_and_honorarios(self) -> None:
        rows = [
            self.row(valor_total_acordo=1000, valor_entrada=200, gamma_valor_ho=100),
            self.row(
                id=2,
                valor_total_acordo=3000,
                valor_entrada=500,
                tipo_acordo="PARCELADO",
                gamma_valor_ho=300,
            ),
        ]

        analysis = self.service._wallet_analysis(
            rows,
            {"period_scope": "month", "month": 7, "year": 2026},
        )[0]

        self.assertEqual(analysis["total_value"], 4000)
        self.assertEqual(analysis["entry_value"], 700)
        self.assertEqual(analysis["installment_entry"], 500)
        self.assertEqual(analysis["paid_honorarios"], 400)
        self.assertEqual(analysis["honorarios"]["expected"], 400)
        self.assertEqual(analysis["honorarios"]["received"], 400)
        self.assertEqual(analysis["gecors"][0]["value"], "4962")
        self.assertEqual(analysis["states"][0]["value"], "SP")
        self.assertEqual(analysis["funnel"][2]["count"], 2)

    def test_wallet_trend_exposes_all_interactive_chart_metrics(self) -> None:
        rows = [
            self.row(id=1, valor_total_acordo=1000, status="PAGAMENTO_REALIZADO", tipo_acordo="A_VISTA", gamma_valor_ho=100),
            self.row(id=2, valor_total_acordo=2000, status="QUEBRA", tipo_acordo="PARCELADO", gamma_valor_ho=200),
            self.row(id=3, valor_total_acordo=3000, status="PROPOSTA_NEGADA", tipo_acordo="PARCELADO", gamma_valor_ho=300),
        ]

        trend = self.service._wallet_trend(
            rows,
            {"period_scope": "month", "month": 7, "year": 2026},
            "GAMMA",
        )[0]

        self.assertEqual(trend["total_value"], 6000)
        self.assertEqual(trend["paid_value"], 1000)
        self.assertEqual(trend["paid_honorarios"], 100)
        self.assertEqual(trend["cash_value"], 1000)
        self.assertEqual(trend["installment_total"], 5000)
        self.assertEqual(trend["breaks_value"], 2000)
        self.assertEqual(trend["negated_value"], 3000)

    def test_wallet_metric_filter_uses_status_and_agreement_type(self) -> None:
        paid = self.row(status="PAGAMENTO_REALIZADO", tipo_acordo="A_VISTA")
        broken = self.row(status="QUEBRA", tipo_acordo="PARCELADO")

        self.assertTrue(self.service._row_matches_wallet_metric(paid, "paid_honorarios"))
        self.assertTrue(self.service._row_matches_wallet_metric(paid, "cash_value"))
        self.assertTrue(self.service._row_matches_wallet_metric(broken, "breaks_value"))
        self.assertTrue(self.service._row_matches_wallet_metric(broken, "installment_total"))
        self.assertFalse(self.service._row_matches_wallet_metric(broken, "paid_value"))

    def test_wallet_dimensions_aggregate_values_and_unidentified_records(self) -> None:
        rows = [
            self.row(valor_total_acordo=1000, valor_entrada=100, uf="SP", gecor="4962"),
            self.row(id=2, valor_total_acordo=500, valor_entrada=50, uf="SP", gecor="4962"),
            self.row(id=3, valor_total_acordo=250, valor_entrada=0, uf="", gecor=""),
        ]

        states = self.service._wallet_dimension(rows, "uf")
        gecors = self.service._wallet_dimension(rows, "gecor")

        self.assertEqual(states[0]["value"], "SP")
        self.assertEqual(states[0]["agreements"], 2)
        self.assertEqual(states[0]["total_value"], 1500)
        self.assertEqual(states[1]["value"], "NAO INFORMADO")
        self.assertEqual(gecors[0]["value"], "4962")

    def test_alpha_wallet_analysis_uses_entry_and_portfolio_goal(self) -> None:
        self.service._alpha_portfolio_goals = lambda _filters: {
            "PORTFOLIOA": {"goal": 2000, "source": "PDF"}
        }
        rows = [
            self.row(
                carteira="ALPHA",
                portfolio="Portfolio A",
                tipo_acordo="PARCELADO",
                valor_total_acordo=10000,
                valor_entrada=1500,
                gamma_valor_ho=0,
                dynamic_honorarios=225,
            ),
        ]

        analysis = self.service._wallet_analysis(
            rows,
            {"period_scope": "month", "month": 7, "year": 2026},
        )[0]
        portfolio = analysis["portfolios"][0]

        self.assertEqual(portfolio["base_value"], 1500)
        self.assertEqual(portfolio["goal"], 2000)
        self.assertEqual(portfolio["goal_attainment"], 75)

    def test_beta_wallet_analysis_groups_records_by_polo(self) -> None:
        rows = [
            self.row(
                carteira="BETA",
                portfolio="ATIVO",
                tipo_acordo="A_VISTA",
                valor_total_acordo=2500,
                valor_entrada=0,
                gamma_valor_ho=0,
                dynamic_honorarios=550,
            ),
        ]

        analysis = self.service._wallet_analysis(
            rows,
            {"period_scope": "month", "month": 7, "year": 2026},
        )[0]

        self.assertEqual(analysis["cash_value"], 2500)
        self.assertEqual(analysis["portfolios"][0]["portfolio"], "ATIVO")
        self.assertEqual(analysis["portfolios"][0]["base_value"], 2500)


if __name__ == "__main__":
    unittest.main()
