from __future__ import annotations

import json
import sqlite3
from datetime import datetime
from typing import Any

from services.production_pdf_report_service import ProductionPdfReportService


class NegocialReportingMixin:
    def producao_mensal(self, carteira: str, mes: int, ano: int) -> dict[str, Any]:
        carteira = self._clean_required(carteira, "Carteira").upper()
        mes = int(mes)
        ano = int(ano)
        if mes < 1 or mes > 12:
            raise ValueError("Mes invalido.")
        if ano < 2000 or ano > 2100:
            raise ValueError("Ano invalido.")

        if self.database_backend == "postgresql":
            records = self._producao_mensal_postgres(carteira, mes, ano)
        else:
            records = self._producao_mensal_sqlite(carteira, mes, ano)

        headers, rows = self._build_producao_rows_for_carteira(carteira, records, include_monthly_meta=True)
        report = self._build_monthly_report(carteira, mes, ano, rows, headers)
        return {
            "carteira": carteira,
            "mes": mes,
            "ano": ano,
            "mes_nome": self._month_name(mes),
            "headers": headers,
            "rows": rows,
            "row_count": len(rows),
            "report": report,
            "fechamento": self.monthly_closing_status(carteira, mes, ano, rows=rows, report=report),
        }

    def producao_mensal_csv(self, filters: dict[str, Any]) -> tuple[str, bytes]:
        filename, headers, rows = self._producao_report_rows(filters, extension="csv")
        return filename, self.report_export.csv_bytes(headers, rows, self._csv_value)

    def producao_mensal_xlsx(self, filters: dict[str, Any]) -> tuple[str, bytes]:
        filename, headers, rows = self._producao_report_rows(filters, extension="xlsx")
        return filename, self.report_export.xlsx_bytes("Producao", headers, rows, self._csv_value)

    def producao_mensal_pdf(self, filters: dict[str, Any]) -> tuple[str, bytes]:
        filename, headers, rows = self._producao_report_rows(filters, extension="pdf")
        options = dict(filters)
        month_names = ["Janeiro", "Fevereiro", "Março", "Abril", "Maio", "Junho", "Julho", "Agosto", "Setembro", "Outubro", "Novembro", "Dezembro"]
        months = self._parse_report_period_selection(filters.get("mes"), 1, 12, "Mes")
        years = self._parse_report_period_selection(filters.get("ano"), 2000, 2100, "Ano")
        month_label = "Todos os meses" if months is None else ", ".join(month_names[month - 1] for month in months)
        year_label = "Todos os anos" if years is None else ", ".join(str(year) for year in years)
        options["periodo"] = f"{month_label} de {year_label}" if month_label != "Todos os meses" else f"{month_label} - {year_label}"
        options["carteira"] = filters.get("carteira", "")
        options["status_label"] = str(filters.get("status_label") or "Todos os status")
        return filename, ProductionPdfReportService().pdf_bytes(headers, rows, options, self._csv_value)

    def monthly_closing_status(
        self,
        carteira: str,
        mes: int,
        ano: int,
        rows: list[dict[str, Any]] | None = None,
        report: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        carteira = self._clean_required(carteira, "Carteira").upper()
        mes = self._validate_month(mes)
        ano = self._validate_year(ano)
        if rows is None or report is None:
            records = self._producao_mensal_postgres(carteira, mes, ano) if self.database_backend == "postgresql" else self._producao_mensal_sqlite(carteira, mes, ano)
            headers, rows = self._build_producao_rows_for_carteira(carteira, records, include_monthly_meta=True)
            report = self._build_monthly_report(carteira, mes, ano, rows, headers)
        open_rows = [
            row for row in rows
            if self._normalize_report_status(row.get("STATUS")) in {"PROPOSTA", "AGUARDANDO_PAGAMENTO"}
        ]
        closed = self._monthly_closing_record(carteira, mes, ano)
        return {
            "carteira": carteira,
            "mes": mes,
            "ano": ano,
            "mes_nome": self._month_name(mes),
            "closed": bool(closed),
            "closed_at": closed.get("closed_at") if closed else "",
            "closed_by": closed.get("closed_by") if closed else "",
            "open_count": len(open_rows),
            "open_rows": open_rows[:200],
            "status": report.get("status", {}),
            "report": report,
        }

    def close_month(self, carteira: str, mes: int, ano: int, usuario: str) -> dict[str, Any]:
        carteira = self._clean_required(carteira, "Carteira").upper()
        mes = self._validate_month(mes)
        ano = self._validate_year(ano)
        usuario = str(usuario or "gerencial").strip() or "gerencial"
        if self.database_backend == "postgresql":
            with self._connect_postgres() as conn:
                if self._monthly_closing_record_postgres(conn, carteira, mes, ano):
                    raise ValueError("Este periodo ja esta fechado.")
                result = conn.execute(
                    """
                    UPDATE producao_registros
                    SET status = 'QUEBRA',
                        justificativa_status = %s,
                        data_pagamento = NULL,
                        updated_at = NOW()
                    WHERE UPPER(COALESCE(carteira, '')) = %s
                      AND EXTRACT(MONTH FROM data_acordo) = %s
                      AND EXTRACT(YEAR FROM data_acordo) = %s
                      AND status IN ('PROPOSTA', 'AGUARDANDO_PAGAMENTO')
                    """,
                    (self.MONTH_CLOSE_BREAK_JUSTIFICATIVA, carteira, mes, ano),
                )
                affected = int(result.rowcount or 0)
                conn.execute(
                    """
                    INSERT INTO fechamento_mensal (carteira, mes, ano, status, closed_by, closed_at, metadata_json)
                    VALUES (%s, %s, %s, 'FECHADO', %s, NOW(), %s::jsonb)
                    """,
                    (carteira, mes, ano, usuario, json.dumps({"quebras_aplicadas": affected}, ensure_ascii=False)),
                )
        else:
            with self.connect() as conn:
                self._ensure_expected_schema(conn)
                self._ensure_monthly_closing_schema_sqlite(conn)
                if self._monthly_closing_record_sqlite(conn, carteira, mes, ano):
                    raise ValueError("Este periodo ja esta fechado.")
                result = conn.execute(
                    """
                    UPDATE producao_registros
                    SET status = 'QUEBRA',
                        justificativa_status = ?,
                        data_pagamento = NULL,
                        updated_at = ?
                    WHERE UPPER(COALESCE(carteira, '')) = ?
                      AND CAST(strftime('%m', data_acordo) AS INTEGER) = ?
                      AND CAST(strftime('%Y', data_acordo) AS INTEGER) = ?
                      AND status IN ('PROPOSTA', 'AGUARDANDO_PAGAMENTO')
                    """,
                    (self.MONTH_CLOSE_BREAK_JUSTIFICATIVA, datetime.now().isoformat(timespec="seconds"), carteira, mes, ano),
                )
                affected = int(result.rowcount or 0)
                conn.execute(
                    """
                    INSERT INTO fechamento_mensal (carteira, mes, ano, status, closed_by, closed_at, metadata_json)
                    VALUES (?, ?, ?, 'FECHADO', ?, ?, ?)
                    """,
                    (
                        carteira,
                        mes,
                        ano,
                        usuario,
                        datetime.now().isoformat(timespec="seconds"),
                        json.dumps({"quebras_aplicadas": affected}, ensure_ascii=False),
                    ),
                )
        status_payload = self.monthly_closing_status(carteira, mes, ano)
        status_payload["quebras_aplicadas"] = affected
        return status_payload

    def monthly_closing_report_xlsx(self, carteira: str, mes: int, ano: int) -> tuple[str, bytes]:
        carteira = self._clean_required(carteira, "Carteira").upper()
        mes = self._validate_month(mes)
        ano = self._validate_year(ano)
        payload = self.producao_mensal(carteira, mes, ano)
        filename = f"fechamento_{self._filename_slug(carteira)}_{ano}_{mes:02d}.xlsx"
        return filename, self.report_export.xlsx_bytes("Fechamento", payload["headers"], payload["rows"], self._csv_value)

    def _validate_month(self, value: Any) -> int:
        mes = int(value)
        if mes < 1 or mes > 12:
            raise ValueError("Mes invalido.")
        return mes

    def _validate_year(self, value: Any) -> int:
        ano = int(value)
        if ano < 2000 or ano > 2100:
            raise ValueError("Ano invalido.")
        return ano

    def _ensure_monthly_closing_schema_sqlite(self, conn: sqlite3.Connection) -> None:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS fechamento_mensal (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                carteira TEXT NOT NULL,
                mes INTEGER NOT NULL,
                ano INTEGER NOT NULL,
                status TEXT NOT NULL DEFAULT 'FECHADO',
                closed_by TEXT NOT NULL,
                closed_at TEXT NOT NULL,
                metadata_json TEXT NOT NULL DEFAULT '{}',
                UNIQUE (carteira, mes, ano)
            )
            """
        )
        conn.execute("CREATE INDEX IF NOT EXISTS ix_negocial_fechamento_mensal_periodo ON fechamento_mensal (carteira, ano, mes)")

    def _monthly_closing_record(self, carteira: str, mes: int, ano: int) -> dict[str, Any] | None:
        if self.database_backend == "postgresql":
            with self._connect_postgres() as conn:
                return self._monthly_closing_record_postgres(conn, carteira, mes, ano)
        with self.connect() as conn:
            self._ensure_expected_schema(conn)
            self._ensure_monthly_closing_schema_sqlite(conn)
            return self._monthly_closing_record_sqlite(conn, carteira, mes, ano)

    def _monthly_closing_record_postgres(self, conn, carteira: str, mes: int, ano: int) -> dict[str, Any] | None:
        row = conn.execute(
            """
            SELECT carteira, mes, ano, status, closed_by, closed_at::text AS closed_at, metadata_json::text AS metadata_json
            FROM fechamento_mensal
            WHERE UPPER(carteira) = %s AND mes = %s AND ano = %s
            """,
            (str(carteira or "").upper(), int(mes), int(ano)),
        ).fetchone()
        return dict(row) if row else None

    def _monthly_closing_record_sqlite(self, conn: sqlite3.Connection, carteira: str, mes: int, ano: int) -> dict[str, Any] | None:
        row = conn.execute(
            """
            SELECT carteira, mes, ano, status, closed_by, closed_at, metadata_json
            FROM fechamento_mensal
            WHERE UPPER(carteira) = ? AND mes = ? AND ano = ?
            """,
            (str(carteira or "").upper(), int(mes), int(ano)),
        ).fetchone()
        return dict(row) if row else None

    def _ensure_month_open_postgres(self, conn, carteira: str, data_acordo: Any) -> None:
        parsed = self._date_from_db_value(data_acordo)
        if not parsed:
            return
        if self._monthly_closing_record_postgres(conn, str(carteira or "").upper(), parsed.month, parsed.year):
            raise ValueError("Este periodo esta fechado e nao permite alteracoes.")

    def _ensure_month_open_sqlite(self, conn: sqlite3.Connection, carteira: str, data_acordo: Any) -> None:
        parsed = self._date_from_db_value(data_acordo)
        if not parsed:
            return
        self._ensure_monthly_closing_schema_sqlite(conn)
        if self._monthly_closing_record_sqlite(conn, str(carteira or "").upper(), parsed.month, parsed.year):
            raise ValueError("Este periodo esta fechado e nao permite alteracoes.")

    def _producao_report_rows(self, filters: dict[str, Any], extension: str) -> tuple[str, list[str], list[dict[str, Any]]]:
        carteira = self._clean_required(filters.get("carteira", ""), "Carteira").upper()
        usuario = str(filters.get("usuario") or "").strip()
        dia = str(filters.get("dia") or "").strip()
        status = str(filters.get("status") or "").strip()
        selected_months = self._parse_report_period_selection(filters.get("mes"), 1, 12, "Mes")
        selected_years = self._parse_report_period_selection(filters.get("ano"), 2000, 2100, "Ano")
        records = (
            self._producao_carteira_postgres(carteira)
            if self.database_backend == "postgresql"
            else self._producao_carteira_sqlite(carteira)
        )
        headers, rows = self._build_producao_rows_for_carteira(carteira, records, include_monthly_meta=True)
        rows = [
            row for row in rows
            if self._report_row_matches_period(row, selected_months, selected_years)
        ]
        rows = self._filter_report_rows(rows, usuario=usuario, dia=dia, status=status)

        if self._is_alpha(carteira):
            headers.append("ULTIMA ATUALIZACAO")
        if self._report_has_multiple_periods(selected_months, selected_years):
            headers = [header for header in headers if self._header_key(header) != "COMPETENCIA"]
            headers.append("COMPETENCIA")
            for row in rows:
                row["COMPETENCIA"] = self._report_competence_label(row)
        scope = self._filename_slug(usuario or "carteira")
        year_slug = "todos_anos" if selected_years is None else "-".join(str(year) for year in selected_years)
        month_slug = "todos_meses" if selected_months is None else "-".join(f"{month:02d}" for month in selected_months)
        filename = f"relatorio_producao_{self._filename_slug(carteira)}_{year_slug}_{month_slug}_{scope}.{extension}"
        return filename, headers, rows

    def _parse_report_period_selection(
        self, value: Any, minimum: int, maximum: int, label: str
    ) -> list[int] | None:
        text = str(value or "").strip().lower()
        if text in {"", "todos", "all"}:
            return None
        values: list[int] = []
        for raw_item in text.split(","):
            try:
                item = int(raw_item.strip())
            except (TypeError, ValueError) as exc:
                raise ValueError(f"{label} invalido.") from exc
            if item < minimum or item > maximum:
                raise ValueError(f"{label} invalido.")
            if item not in values:
                values.append(item)
        if not values:
            raise ValueError(f"Selecione ao menos um {label.lower()}.")
        return sorted(values)

    def _report_row_competence(self, row: dict[str, Any]):
        competence = str(row.get("competencia") or "").strip()
        parsed = self._date_from_db_value(f"{competence}-01" if len(competence) == 7 else competence)
        if parsed:
            return parsed
        return self._date_from_db_value(row.get("DATA ACORDO") or row.get("DATA"))

    def _report_row_matches_period(
        self, row: dict[str, Any], months: list[int] | None, years: list[int] | None
    ) -> bool:
        competence = self._report_row_competence(row)
        if not competence:
            return False
        return (months is None or competence.month in months) and (years is None or competence.year in years)

    def _report_has_multiple_periods(self, months: list[int] | None, years: list[int] | None) -> bool:
        return months is None or years is None or len(months) * len(years) > 1

    def _report_competence_label(self, row: dict[str, Any]) -> str:
        competence = self._report_row_competence(row)
        return competence.strftime("%m/%Y") if competence else ""
