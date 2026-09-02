from services.negocial_production_mixin import NegocialProductionMixin


class ReportFilterHarness(NegocialProductionMixin):
    @staticmethod
    def _normalize_report_status(value):
        return str(value or "").strip().upper().replace(" ", "_")


def test_report_filter_accepts_multiple_statuses():
    service = ReportFilterHarness()
    rows = [
        {"CLIENTE": "Alfa", "STATUS": "Proposta"},
        {"CLIENTE": "Beta", "STATUS": "Aguardando pagamento"},
        {"CLIENTE": "Gama", "STATUS": "Pagamento realizado"},
    ]

    filtered = service._filter_report_rows(rows, status="PROPOSTA,AGUARDANDO_PAGAMENTO")

    assert [row["CLIENTE"] for row in filtered] == ["Alfa", "Beta"]


def test_report_filter_keeps_all_rows_when_statuses_are_empty():
    service = ReportFilterHarness()
    rows = [{"STATUS": "Proposta"}, {"STATUS": "Quebra"}]

    assert service._filter_report_rows(rows, status="") == rows
