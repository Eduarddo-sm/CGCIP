from decimal import Decimal

from services.production_pdf_report_service import ProductionPdfReportService


def _format(value):
    if value in (None, ""):
        return "Vazio"
    if isinstance(value, Decimal):
        return f"R$ {value:.2f}"
    return str(value)


def test_pdf_report_is_generated_with_grouping_fields_hidden_from_table():
    headers = [
        "NPJ",
        "CLIENTE",
        "NEGOCIADOR",
        "STATUS",
        "VALOR DO ACORDO",
        "HONORARIOS RECEBIDOS",
        "DATA DE VENCIMENTO",
        "JUSTIFICATIVA",
    ]
    rows = [
        {
            "NPJ": "20260000000001",
            "CLIENTE": "Cliente Alfa",
            "NEGOCIADOR": "ana.silva",
            "STATUS": "AGUARDANDO PAGAMENTO",
            "VALOR DO ACORDO": Decimal("15000.00"),
            "HONORARIOS RECEBIDOS": Decimal("1500.00"),
            "DATA DE VENCIMENTO": "12/08/2026",
            "JUSTIFICATIVA": "Confirmar comprovante.",
        },
        {
            "NPJ": "20260000000002",
            "CLIENTE": "Cliente Beta",
            "NEGOCIADOR": "bruno.santos",
            "STATUS": "AGUARDANDO PAGAMENTO",
            "VALOR DO ACORDO": Decimal("8200.00"),
            "HONORARIOS RECEBIDOS": Decimal("820.00"),
            "DATA DE VENCIMENTO": "13/08/2026",
            "JUSTIFICATIVA": "Cobrar retorno do cliente.",
        },
    ]

    content = ProductionPdfReportService().pdf_bytes(
        headers,
        rows,
        {
            "titulo": "Acompanhamento de pagamentos",
            "carteira": "GAMMA",
            "periodo": "Agosto de 2026",
            "status_label": "Aguardando pagamento",
            "agrupar_por": "negociador",
            "campos": "cliente,identificador,status,valor,honorarios,vencimento,justificativa",
            "orientacao": "paisagem",
        },
        _format,
    )

    assert content.startswith(b"%PDF-")
    assert content.rstrip().endswith(b"%%EOF")
    assert len(content) > 2_000


def test_pdf_report_supports_empty_result():
    content = ProductionPdfReportService().pdf_bytes(
        ["CLIENTE", "STATUS"],
        [],
        {"titulo": "Sem pendencias", "campos": "cliente,status"},
        _format,
    )

    assert content.startswith(b"%PDF-")
    assert len(content) > 1_000


def test_pdf_formats_currency_and_dates_for_display():
    service = ProductionPdfReportService()

    assert service._display_value("valor", "1234.56", _format) == "R$ 1.234,56"
    assert service._display_value("honorarios", Decimal("98765.40"), _format) == "R$ 98.765,40"
    assert service._display_value("data", "2026-08-13T15:42:00", _format) == "13/08/2026"
    assert service._display_value("vencimento", "14/09/2026", _format) == "14/09/2026"
