from __future__ import annotations

import io
import re
import unicodedata
from collections import OrderedDict
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from html import escape
from typing import Any

from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT, TA_RIGHT
from reportlab.lib.pagesizes import A4, landscape, portrait
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import (
    KeepTogether,
    LongTable,
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)


class ProductionPdfReportService:
    FIELD_ALIASES = OrderedDict([
        ("cliente", ("CLIENTE", "NOME CLIENTE", "NOME")),
        ("identificador", ("NPJ", "DEBIT ID", "SUITID", "CPF/CNPJ", "CPF", "CNPJ", "CONTRATO", "PROCESSO")),
        ("negociador", ("NEGOCIADOR", "USUARIO", "OPERADOR")),
        ("status", ("STATUS",)),
        ("valor", ("VALOR DO ACORDO", "VALOR TOTAL", "VALOR FECHADO", "VALOR TOTAL DO DEBITO")),
        ("entrada", ("VALOR DA ENTRADA", "ENTRADA", "VALOR MINIMO PRE APROVADO")),
        ("honorarios", ("HONORARIOS RECEBIDOS", "HONORÁRIOS RECEBIDOS", "HONORARIOS", "HONORÁRIOS", "H.O", "H O")),
        ("data", ("DATA ACORDO", "DATA", "COMPETENCIA")),
        ("vencimento", ("DATA DE VENCIMENTO", "VENCIMENTO")),
        ("pagamento", ("DATA DO PAGAMENTO", "DATA PAGAMENTO")),
        ("justificativa", ("JUSTIFICATIVA", "MOTIVO", "OBSERVACAO", "OBSERVAÇÃO")),
    ])

    FIELD_LABELS = {
        "cliente": "Cliente",
        "identificador": "Identificador",
        "negociador": "Negociador",
        "status": "Status",
        "valor": "Valor do acordo",
        "entrada": "Entrada",
        "honorarios": "Honorários",
        "data": "Data do acordo",
        "vencimento": "Vencimento",
        "pagamento": "Pagamento",
        "justificativa": "Justificativa",
    }

    def pdf_bytes(
        self,
        headers: list[str],
        rows: list[dict[str, Any]],
        options: dict[str, Any],
        value_formatter,
    ) -> bytes:
        orientation = str(options.get("orientacao") or "paisagem").lower()
        pagesize = landscape(A4) if orientation != "retrato" else portrait(A4)
        output = io.BytesIO()
        document = SimpleDocTemplate(
            output,
            pagesize=pagesize,
            leftMargin=13 * mm,
            rightMargin=13 * mm,
            topMargin=16 * mm,
            bottomMargin=14 * mm,
            title=str(options.get("titulo") or "Relatório de acompanhamento"),
            author="Sistema Gerencial",
        )
        styles = self._styles()
        resolved = self._resolve_columns(headers, options.get("campos"))
        semantic_columns = dict(self._resolve_columns(headers, ",".join(self.FIELD_ALIASES.keys())))
        ordered_rows = self._ordered_rows(rows, semantic_columns, str(options.get("ordenacao") or "valor_desc"))
        groups = self._group_rows(ordered_rows, semantic_columns, str(options.get("agrupar_por") or "negociador"))

        story = [
            Paragraph(escape(str(options.get("titulo") or "Relatório de acompanhamento da Produção Diária")), styles["title"]),
            Paragraph(escape(self._subtitle(options, len(rows))), styles["subtitle"]),
            Spacer(1, 5 * mm),
            self._summary_table(rows, semantic_columns, styles),
        ]
        notes = str(options.get("observacoes") or "").strip()
        if notes:
            story.extend([
                Spacer(1, 4 * mm),
                Paragraph("Orientação para acompanhamento", styles["section"]),
                Paragraph(escape(notes).replace("\n", "<br/>"), styles["body"]),
            ])
        story.append(Spacer(1, 4 * mm))

        if not rows:
            story.append(Paragraph("Nenhum caso encontrado para os filtros selecionados.", styles["empty"]))
        else:
            for index, (group_name, group_rows) in enumerate(groups.items()):
                if index and options.get("quebrar_grupo"):
                    story.append(PageBreak())
                group_heading = [
                    Paragraph(f"{escape(group_name)} <font color='#64748B'>· {len(group_rows)} caso(s)</font>", styles["group"]),
                    Spacer(1, 1.5 * mm),
                ]
                records_table = self._records_table(group_rows, resolved, value_formatter, styles, document.width)
                if len(group_rows) <= 3:
                    story.append(KeepTogether([*group_heading, records_table]))
                else:
                    story.extend(group_heading)
                    story.append(records_table)
                story.append(Spacer(1, 4 * mm))

        generated = datetime.now().strftime("%d/%m/%Y às %H:%M")
        document.build(story, onFirstPage=lambda canvas, doc: self._page(canvas, doc, generated), onLaterPages=lambda canvas, doc: self._page(canvas, doc, generated))
        return output.getvalue()

    def _resolve_columns(self, headers: list[str], requested: Any) -> list[tuple[str, str]]:
        normalized = {self._normalize(header): header for header in headers}
        requested_keys = [key for key in str(requested or "").split(",") if key in self.FIELD_ALIASES]
        if not requested_keys:
            requested_keys = ["cliente", "identificador", "negociador", "status", "valor", "honorarios", "vencimento", "justificativa"]
        resolved: list[tuple[str, str]] = []
        for key in requested_keys:
            header = next((normalized.get(self._normalize(alias)) for alias in self.FIELD_ALIASES[key] if normalized.get(self._normalize(alias))), None)
            if header and header not in [item[1] for item in resolved]:
                resolved.append((key, header))
        if resolved:
            return resolved
        return [("cliente", headers[0])] if headers else []

    def _ordered_rows(self, rows: list[dict[str, Any]], header_by_key: dict[str, str], order: str) -> list[dict[str, Any]]:
        result = list(rows)
        if order == "cliente":
            return sorted(result, key=lambda row: self._normalize(row.get(header_by_key.get("cliente", ""))))
        if order == "data":
            return sorted(result, key=lambda row: str(row.get(header_by_key.get("vencimento", header_by_key.get("data", ""))) or ""))
        money_header = header_by_key.get("valor") or header_by_key.get("honorarios") or ""
        return sorted(result, key=lambda row: self._decimal(row.get(money_header)) or Decimal("0"), reverse=True)

    def _group_rows(self, rows: list[dict[str, Any]], header_by_key: dict[str, str], group_by: str) -> OrderedDict[str, list[dict[str, Any]]]:
        if group_by == "none":
            return OrderedDict([("Casos selecionados", rows)])
        header = header_by_key.get("status" if group_by == "status" else "negociador", "")
        groups: OrderedDict[str, list[dict[str, Any]]] = OrderedDict()
        for row in rows:
            name = str(row.get(header) or "Não informado").strip() or "Não informado"
            groups.setdefault(name, []).append(row)
        return OrderedDict(sorted(groups.items(), key=lambda item: self._normalize(item[0])))

    def _summary_table(self, rows: list[dict[str, Any]], header_by_key: dict[str, str], styles) -> Table:
        total_value = sum((self._decimal(row.get(header_by_key.get("valor", ""))) or Decimal("0") for row in rows), Decimal("0"))
        total_ho = sum((self._decimal(row.get(header_by_key.get("honorarios", ""))) or Decimal("0") for row in rows), Decimal("0"))
        negotiators = len({str(row.get(header_by_key.get("negociador", "")) or "").strip() for row in rows if str(row.get(header_by_key.get("negociador", "")) or "").strip()})
        cells = [
            self._metric("CASOS", f"{len(rows):,}".replace(",", "."), styles),
            self._metric("NEGOCIADORES", str(negotiators), styles),
            self._metric("VALOR DOS ACORDOS", self._money(total_value), styles),
            self._metric("HONORÁRIOS", self._money(total_ho), styles),
        ]
        table = Table([cells], colWidths=[25.5 * mm, 31 * mm, 52 * mm, 45 * mm], hAlign="LEFT")
        table.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"), ("LEFTPADDING", (0, 0), (-1, -1), 0), ("RIGHTPADDING", (0, 0), (-1, -1), 5 * mm)]))
        return table

    @staticmethod
    def _metric(label: str, value: str, styles) -> Table:
        table = Table([[Paragraph(label, styles["metric_label"])], [Paragraph(value, styles["metric_value"])]], colWidths=[42 * mm])
        table.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#F1F5F9")), ("BOX", (0, 0), (-1, -1), .5, colors.HexColor("#CBD5E1")), ("LEFTPADDING", (0, 0), (-1, -1), 8), ("RIGHTPADDING", (0, 0), (-1, -1), 8), ("TOPPADDING", (0, 0), (-1, -1), 5), ("BOTTOMPADDING", (0, 0), (-1, -1), 5)]))
        return table

    def _records_table(self, rows, columns, value_formatter, styles, available_width) -> LongTable:
        labels = [self.FIELD_LABELS.get(key, header.title()) for key, header in columns]
        widths = self._column_widths(columns, available_width)
        data = [[Paragraph(escape(label), styles["table_header"]) for label in labels]]
        for row in rows:
            data.append([
                Paragraph(
                    escape(self._display_value(key, row.get(header), value_formatter)),
                    styles["table_cell_money" if key in {"valor", "entrada", "honorarios"} else "table_cell"],
                )
                for key, header in columns
            ])
        table = LongTable(data, colWidths=widths, repeatRows=1, hAlign="LEFT")
        table.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#17365D")),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("GRID", (0, 0), (-1, -1), .35, colors.HexColor("#CBD5E1")),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#F8FAFC")]),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("LEFTPADDING", (0, 0), (-1, -1), 5),
            ("RIGHTPADDING", (0, 0), (-1, -1), 5),
            ("TOPPADDING", (0, 0), (-1, -1), 5),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ]))
        return table

    @staticmethod
    def _column_widths(columns, width):
        weights = {"cliente": 2.3, "identificador": 1.35, "negociador": 1.3, "status": 1.25, "valor": 1.2, "entrada": 1.1, "honorarios": 1.1, "data": 1.0, "vencimento": 1.0, "pagamento": 1.0, "justificativa": 2.2}
        total = sum(weights.get(key, 1) for key, _ in columns) or 1
        return [width * weights.get(key, 1) / total for key, _ in columns]

    def _subtitle(self, options, count):
        wallet = str(options.get("carteira") or "Todas").upper()
        period = str(options.get("periodo") or "Período selecionado")
        status = str(options.get("status_label") or "Todos os status")
        return f"Carteira {wallet}  |  {period}  |  {status}  |  {count} caso(s)"

    @staticmethod
    def _styles():
        base = getSampleStyleSheet()
        return {
            "title": ParagraphStyle("ReportTitle", parent=base["Title"], fontName="Helvetica-Bold", fontSize=19, leading=23, textColor=colors.HexColor("#0F172A"), alignment=TA_LEFT, spaceAfter=2),
            "subtitle": ParagraphStyle("ReportSubtitle", parent=base["Normal"], fontName="Helvetica", fontSize=8.5, leading=11, textColor=colors.HexColor("#64748B")),
            "section": ParagraphStyle("ReportSection", parent=base["Heading2"], fontName="Helvetica-Bold", fontSize=10, leading=13, textColor=colors.HexColor("#17365D"), spaceAfter=4),
            "group": ParagraphStyle("ReportGroup", parent=base["Heading3"], fontName="Helvetica-Bold", fontSize=10, leading=13, textColor=colors.HexColor("#0F172A")),
            "body": ParagraphStyle("ReportBody", parent=base["Normal"], fontName="Helvetica", fontSize=8.5, leading=12, textColor=colors.HexColor("#334155"), borderColor=colors.HexColor("#CBD5E1"), borderWidth=.5, borderPadding=7, backColor=colors.HexColor("#F8FAFC")),
            "empty": ParagraphStyle("ReportEmpty", parent=base["Normal"], fontName="Helvetica", fontSize=10, textColor=colors.HexColor("#64748B"), alignment=TA_LEFT),
            "metric_label": ParagraphStyle("MetricLabel", parent=base["Normal"], fontName="Helvetica-Bold", fontSize=6.8, leading=8, textColor=colors.HexColor("#64748B")),
            "metric_value": ParagraphStyle("MetricValue", parent=base["Normal"], fontName="Helvetica-Bold", fontSize=11, leading=14, textColor=colors.HexColor("#0F172A")),
            "table_header": ParagraphStyle("TableHeader", parent=base["Normal"], fontName="Helvetica-Bold", fontSize=7, leading=8, textColor=colors.white),
            "table_cell": ParagraphStyle("TableCell", parent=base["Normal"], fontName="Helvetica", fontSize=7, leading=9, textColor=colors.HexColor("#1E293B")),
            "table_cell_money": ParagraphStyle("TableCellMoney", parent=base["Normal"], fontName="Helvetica", fontSize=7, leading=9, textColor=colors.HexColor("#1E293B"), alignment=TA_RIGHT),
        }

    @staticmethod
    def _page(canvas, document, generated):
        canvas.saveState()
        canvas.setStrokeColor(colors.HexColor("#CBD5E1"))
        canvas.line(document.leftMargin, 10 * mm, document.pagesize[0] - document.rightMargin, 10 * mm)
        canvas.setFont("Helvetica", 7)
        canvas.setFillColor(colors.HexColor("#64748B"))
        canvas.drawString(document.leftMargin, 6.5 * mm, f"Gerado pelo Sistema Gerencial em {generated}")
        canvas.drawRightString(document.pagesize[0] - document.rightMargin, 6.5 * mm, f"Página {document.page}")
        canvas.restoreState()

    @staticmethod
    def _normalize(value: Any) -> str:
        text = unicodedata.normalize("NFKD", str(value or "").upper())
        return re.sub(r"[^A-Z0-9]+", " ", "".join(char for char in text if not unicodedata.combining(char))).strip()

    @staticmethod
    def _decimal(value: Any) -> Decimal | None:
        if isinstance(value, Decimal):
            return value
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            return Decimal(str(value))
        text = str(value or "").replace("R$", "").replace(" ", "").replace("\u00a0", "")
        if not text:
            return None
        if "," in text:
            text = text.replace(".", "").replace(",", ".")
        try:
            return Decimal(text)
        except InvalidOperation:
            return None

    def _display_value(self, key: str, value: Any, value_formatter) -> str:
        if value in (None, ""):
            return "-"
        if key in {"valor", "entrada", "honorarios"}:
            decimal_value = self._decimal(value)
            return self._money(decimal_value) if decimal_value is not None else str(value_formatter(value) or "-")
        if key in {"data", "vencimento", "pagamento"}:
            parsed_date = self._date_value(value)
            return parsed_date.strftime("%d/%m/%Y") if parsed_date else str(value_formatter(value) or "-")
        return str(value_formatter(value) or "-")

    @staticmethod
    def _date_value(value: Any) -> date | None:
        if isinstance(value, datetime):
            return value.date()
        if isinstance(value, date):
            return value
        text = str(value or "").strip()
        if not text:
            return None
        iso_candidate = text[:10]
        for candidate, pattern in (
            (iso_candidate, "%Y-%m-%d"),
            (iso_candidate, "%d/%m/%Y"),
            (iso_candidate, "%d-%m-%Y"),
        ):
            try:
                return datetime.strptime(candidate, pattern).date()
            except ValueError:
                continue
        return None

    @staticmethod
    def _money(value: Decimal) -> str:
        formatted = f"{value:,.2f}".replace(",", "_").replace(".", ",").replace("_", ".")
        return f"R$ {formatted}"
