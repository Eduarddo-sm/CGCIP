from datetime import date, datetime

from services.negocial_reporting_mixin import NegocialReportingMixin


class ProductionReportHarness(NegocialReportingMixin):
    database_backend = "sqlite"

    @staticmethod
    def _clean_required(value, label):
        cleaned = str(value or "").strip()
        if not cleaned:
            raise ValueError(f"{label} obrigatoria.")
        return cleaned

    @staticmethod
    def _date_from_db_value(value):
        if isinstance(value, datetime):
            return value.date()
        if isinstance(value, date):
            return value
        text = str(value or "").strip()
        if not text:
            return None
        try:
            return date.fromisoformat(text[:10])
        except ValueError:
            return None

    @staticmethod
    def _header_key(value):
        return str(value or "").strip().upper()

    @staticmethod
    def _filename_slug(value):
        return str(value or "").strip().lower().replace(" ", "_")

    @staticmethod
    def _is_alpha(_carteira):
        return False

    @staticmethod
    def _filter_report_rows(rows, usuario="", dia="", status=""):
        return rows

    @staticmethod
    def _producao_carteira_sqlite(_carteira):
        return []

    @staticmethod
    def _build_producao_rows_for_carteira(_carteira, _records, include_monthly_meta=False):
        return ["CLIENTE"], [
            {"CLIENTE": "Acordo A", "competencia": "2026-01"},
            {"CLIENTE": "Acordo B", "competencia": "2026-02"},
            {"CLIENTE": "Acordo C", "competencia": "2025-01"},
        ]


def test_multiple_months_add_competence_as_last_column():
    service = ProductionReportHarness()

    _, headers, rows = service._producao_report_rows(
        {"carteira": "Teste", "mes": "1,2", "ano": "2026"},
        extension="xlsx",
    )

    assert headers == ["CLIENTE", "COMPETENCIA"]
    assert [(row["CLIENTE"], row["COMPETENCIA"]) for row in rows] == [
        ("Acordo A", "01/2026"),
        ("Acordo B", "02/2026"),
    ]


def test_multiple_years_filter_selected_periods_and_add_competence():
    service = ProductionReportHarness()

    _, headers, rows = service._producao_report_rows(
        {"carteira": "Teste", "mes": "1", "ano": "2025,2026"},
        extension="pdf",
    )

    assert headers[-1] == "COMPETENCIA"
    assert [(row["CLIENTE"], row["COMPETENCIA"]) for row in rows] == [
        ("Acordo A", "01/2026"),
        ("Acordo C", "01/2025"),
    ]


def test_single_competence_does_not_add_export_column():
    service = ProductionReportHarness()

    _, headers, rows = service._producao_report_rows(
        {"carteira": "Teste", "mes": "2", "ano": "2026"},
        extension="csv",
    )

    assert headers == ["CLIENTE"]
    assert rows == [{"CLIENTE": "Acordo B", "competencia": "2026-02"}]


def test_period_parser_deduplicates_and_validates_values():
    service = ProductionReportHarness()

    assert service._parse_report_period_selection("2,1,2", 1, 12, "Mes") == [1, 2]
    assert service._parse_report_period_selection("todos", 1, 12, "Mes") is None
