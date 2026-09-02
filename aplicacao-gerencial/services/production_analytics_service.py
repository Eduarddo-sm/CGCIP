from __future__ import annotations

import calendar
import hashlib
import json
import sqlite3
import threading
import time
import unicodedata
from collections import defaultdict
from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Any


class ProductionAnalyticsService:
    """Aggregates the canonical production model for management dashboards."""

    STATUS_LABELS = {
        "PROPOSTA": "Propostas",
        "AGUARDANDO_PAGAMENTO": "Aguardando pagamento",
        "PAGAMENTO_REALIZADO": "Pagamentos realizados",
        "AGUARDANDO_LEVANTAMENTO": "Aguardando levantamento",
        "PROPOSTA_NEGADA": "Propostas negadas",
        "OPERACAO_RECOMPRADA": "Operações recompradas",
        "QUEBRA": "Quebras",
    }
    STATUS_DETAIL_LABELS = {
        "PROPOSTA": "Proposta",
        "AGUARDANDO_PAGAMENTO": "Aguardando pagamento",
        "PAGAMENTO_REALIZADO": "Pagamento realizado",
        "AGUARDANDO_LEVANTAMENTO": "Aguardando levantamento",
        "PROPOSTA_NEGADA": "Proposta negada",
        "OPERACAO_RECOMPRADA": "Operacao recomprada",
        "QUEBRA": "Quebra",
    }
    OPEN_STATUSES = {"PROPOSTA", "AGUARDANDO_PAGAMENTO"}
    DYNAMIC_HO_KEYS = (
        "HONORARIOS",
        "HONORARIOS_RECEBIDOS",
        "HONORARIO",
        "HONORARIOS_CALCULADOS",
        "H_O",
        "HO",
        "VALOR_HO",
    )

    def __init__(self, negocial: Any, cache_ttl_seconds: int = 45) -> None:
        self.negocial = negocial
        self.cache_ttl_seconds = max(5, int(cache_ttl_seconds))
        self._cache: dict[str, tuple[float, dict[str, Any]]] = {}
        self._lock = threading.RLock()

    def dashboard(self, filters: dict[str, Any] | None = None) -> dict[str, Any]:
        selected = self._normalize_filters(filters or {})
        start, end = self._selected_period_bounds(selected)
        previous_start, previous_end = self._comparison_period(start, selected["period_scope"])
        comparison_start = date(2000, 1, 1)
        comparison_end = date(max(selected["year"], date.today().year) + 1, 1, 1)
        version = self._data_version(start, end, selected)
        comparison_version = self._data_version(comparison_start, comparison_end, selected)
        cache_key = json.dumps(
            {**selected, "version": version, "comparison_version": comparison_version},
            sort_keys=True,
            ensure_ascii=True,
        )

        with self._lock:
            cached = self._cache.get(cache_key)
            if cached and time.monotonic() - cached[0] < self.cache_ttl_seconds:
                return cached[1]

        rows = self._fetch_records(start, end, selected)
        previous_rows = (
            self._fetch_records(previous_start, previous_end, selected)
            if selected["period_scope"] in {"month", "year"}
            else []
        )
        comparison_rows = self._fetch_records(comparison_start, comparison_end, selected)
        payload = self._build_payload(rows, previous_rows, comparison_rows, selected, version)
        with self._lock:
            self._cache = {
                key: value for key, value in self._cache.items()
                if time.monotonic() - value[0] < self.cache_ttl_seconds
            }
            self._cache[cache_key] = (time.monotonic(), payload)
        return payload

    def clear_cache(self) -> None:
        with self._lock:
            self._cache.clear()

    def negotiator_details(self, filters: dict[str, Any] | None = None) -> dict[str, Any]:
        selected = self._normalize_filters(filters or {})
        if not selected["negotiator"]:
            raise ValueError("Informe o negociador.")
        start, end = self._selected_period_bounds(selected)
        rows = self._fetch_records(start, end, selected)
        return {
            "username": selected["negotiator"],
            "period": self._period_metadata(selected, rows),
            "agreements": self._negotiator_agreements(rows),
        }

    def status_details(self, filters: dict[str, Any] | None = None) -> dict[str, Any]:
        selected = self._normalize_filters(filters or {})
        if not selected["status"]:
            raise ValueError("Informe o status.")
        start, end = self._selected_period_bounds(selected)
        rows = self._fetch_records(start, end, selected)
        return {
            "status": selected["status"],
            "status_label": self.STATUS_LABELS.get(selected["status"], selected["status"].replace("_", " ").title()),
            "period": self._period_metadata(selected, rows),
            "agreements": self._negotiator_agreements(rows),
        }

    def dimension_details(self, filters: dict[str, Any] | None = None) -> dict[str, Any]:
        raw = filters or {}
        dimension = str(raw.get("dimension") or "").strip().lower()
        value = str(raw.get("dimension_value") or "").strip()
        if dimension not in {"uf", "gecor"} or not value:
            raise ValueError("Informe uma dimensao valida.")
        selected = self._normalize_filters(raw)
        start, end = self._selected_period_bounds(selected)
        rows = self._fetch_records(start, end, selected)
        normalized_value = value.upper()
        filtered = [
            row for row in rows
            if str(row.get(dimension) or "Nao informado").strip().upper() == normalized_value
        ]
        return {
            "dimension": dimension,
            "dimension_value": value,
            "period": self._period_metadata(selected, filtered),
            "agreements": self._negotiator_agreements(filtered),
        }

    def day_details(self, filters: dict[str, Any] | None = None) -> dict[str, Any]:
        raw = filters or {}
        selected_date = self._as_date(raw.get("selected_date"))
        metric = str(raw.get("metric") or "total_value").strip().lower()
        allowed_metrics = {
            "total_value",
            "paid_honorarios",
            "paid_value",
            "cash_value",
            "installment_total",
            "breaks_value",
            "negated_value",
        }
        if not selected_date or metric not in allowed_metrics:
            raise ValueError("Informe uma data e metrica validas.")
        selected = self._normalize_filters(raw)
        start, end = self._selected_period_bounds(selected)
        rows = self._fetch_records(start, end, selected)
        monthly_granularity = selected.get("period_scope") in {"journey", "year"}
        filtered = [
            row for row in rows
            if (
                (
                    self._metric_reference_date(row, metric, monthly=True)
                    and self._metric_reference_date(row, metric, monthly=True).year == selected_date.year
                    and self._metric_reference_date(row, metric, monthly=True).month == selected_date.month
                )
                if monthly_granularity
                else self._metric_reference_date(row, metric) == selected_date
            )
            and self._row_matches_wallet_metric(row, metric)
        ]
        return {
            "date": selected_date.isoformat(),
            "metric": metric,
            "period": self._period_metadata(selected, filtered),
            "agreements": self._negotiator_agreements(filtered),
        }

    def _normalize_filters(self, filters: dict[str, Any]) -> dict[str, Any]:
        today = date.today()
        period_scope = str(filters.get("period_scope") or filters.get("periodo") or "month").strip().lower()
        if period_scope not in {"month", "year", "journey"}:
            raise ValueError("Periodo invalido.")
        month = int(filters.get("month") or filters.get("mes") or today.month)
        year = int(filters.get("year") or filters.get("ano") or today.year)
        if month < 1 or month > 12:
            raise ValueError("Mes invalido.")
        if year < 2000 or year > 2100:
            raise ValueError("Ano invalido.")
        status = self._normalize_status(filters.get("status"))
        agreement_type = str(filters.get("agreement_type") or filters.get("tipo") or "").strip().upper()
        if agreement_type in {"A VISTA", "A-VISTA", "AVISTA"}:
            agreement_type = "A_VISTA"
        return {
            "wallet": str(filters.get("wallet") or filters.get("carteira") or "").strip().upper(),
            "period_scope": period_scope,
            "month": month,
            "year": year,
            "negotiator": str(filters.get("negotiator") or filters.get("negociador") or "").strip(),
            "status": status,
            "agreement_type": agreement_type,
        }

    def _normalize_status(self, value: Any) -> str:
        text = str(value or "").strip().upper().replace(" ", "_")
        aliases = {
            "PAGO": "PAGAMENTO_REALIZADO",
            "PAGAMENTO": "PAGAMENTO_REALIZADO",
            "NEGADA": "PROPOSTA_NEGADA",
            "PROPOSTA_NEGADO": "PROPOSTA_NEGADA",
            "AGUARDANDO": "AGUARDANDO_PAGAMENTO",
        }
        return aliases.get(text, text)

    def _period_bounds(self, month: int, year: int) -> tuple[date, date]:
        start = date(year, month, 1)
        end = date(year + 1, 1, 1) if month == 12 else date(year, month + 1, 1)
        return start, end

    def _selected_period_bounds(self, filters: dict[str, Any]) -> tuple[date, date]:
        if filters["period_scope"] == "journey":
            today = date.today()
            end = date(today.year + 1, 1, 1) if today.month == 12 else date(today.year, today.month + 1, 1)
            return date(2000, 1, 1), end
        if filters["period_scope"] == "year":
            return date(filters["year"], 1, 1), date(filters["year"] + 1, 1, 1)
        return self._period_bounds(filters["month"], filters["year"])

    def _previous_period(self, start: date) -> tuple[date, date]:
        previous_end = start
        previous_start = date(start.year - 1, 12, 1) if start.month == 1 else date(start.year, start.month - 1, 1)
        return previous_start, previous_end

    def _comparison_period(self, start: date, scope: str) -> tuple[date, date]:
        if scope == "year":
            return date(start.year - 1, 1, 1), start
        return self._previous_period(start)

    def _data_version(self, start: date, end: date, filters: dict[str, Any]) -> str:
        clauses = ["competencia >= {p}", "competencia < {p}"]
        params: list[Any] = [start, end]
        self._append_record_filters(clauses, params, filters, table_alias="")
        placeholder = "%s" if self.negocial.database_backend == "postgresql" else "?"
        where = " AND ".join(clause.format(p=placeholder) for clause in clauses)
        sql = f"""
            SELECT COUNT(*) AS total,
                   MAX(updated_at) AS updated_at,
                   (SELECT MAX(updated_at) FROM user_monthly_goals
                    WHERE competencia >= {placeholder} AND competencia < {placeholder}) AS goal_updated_at
            FROM producao_registros
            WHERE {where}
        """
        with self._connection() as conn:
            row = conn.execute(sql, tuple([start, end, *params])).fetchone()
        values = dict(row) if row else {"total": 0, "updated_at": ""}
        raw = f"{values.get('total', 0)}:{values.get('updated_at') or ''}:{values.get('goal_updated_at') or ''}"
        return hashlib.sha1(raw.encode("utf-8")).hexdigest()[:12]

    def _fetch_records(self, start: date, end: date, filters: dict[str, Any]) -> list[dict[str, Any]]:
        placeholder = "%s" if self.negocial.database_backend == "postgresql" else "?"
        clauses = [f"pr.competencia >= {placeholder}", f"pr.competencia < {placeholder}"]
        params: list[Any] = [start, end]
        self._append_record_filters(clauses, params, filters, table_alias="pr.", placeholder=placeholder)
        dynamic_keys = ", ".join(f"'{key}'" for key in self.DYNAMIC_HO_KEYS)
        sql = f"""
            SELECT
                pr.id,
                pr.competencia,
                pr.data_acordo,
                pr.cliente,
                pr.valor_total_acordo,
                pr.valor_entrada,
                pr.tipo_acordo,
                pr.data_vencimento,
                pr.data_pagamento,
                pr.status,
                pr.justificativa_status,
                pr.carteira,
                pr.created_at,
                pr.updated_at,
                COALESCE(u.username, 'Nao identificado') AS username,
                COALESCE(umg.meta_pagamento, u.meta_pagamento, 0) AS meta_pagamento,
                COALESCE(gamma.valor_ho, 0) AS gamma_valor_ho,
                gamma.producao_id AS gamma_producao_id,
                COALESCE(NULLIF(gamma.gecor, ''), 'Nao informado') AS gecor,
                COALESCE(NULLIF(bg.uf, ''), 'Nao informado') AS uf,
                COALESCE(gamma.percentual_ho, 0) AS gamma_percentual_ho,
                COALESCE(c.usa_percentual_ho, FALSE) AS usa_percentual_ho,
                COALESCE(c.calculo_automatico_ho, FALSE) AS calculo_automatico_ho,
                COALESCE(c.percentual_ho_padrao, 0) AS percentual_ho_padrao,
                COALESCE(gamma.npj, it.debit_id, rt.suitid,
                    (SELECT COALESCE(pc.valor_texto, CAST(pc.valor_numero AS TEXT), CAST(pc.valor_data AS TEXT))
                     FROM producao_campos pc
                     JOIN carteira_colunas cc ON cc.id = pc.coluna_id
                     WHERE pc.producao_id = pr.id AND cc.identificador = TRUE
                     ORDER BY cc.ordem, cc.id LIMIT 1), '') AS identifier,
                COALESCE(NULLIF(it.portfolio, ''),
                    (SELECT COALESCE(pc.valor_texto, CAST(pc.valor_numero AS TEXT))
                     FROM producao_campos pc
                     JOIN carteira_colunas cc ON cc.id = pc.coluna_id
                     WHERE pc.producao_id = pr.id
                       AND UPPER(cc.chave) IN ('PORTFOLIO', 'POLO')
                     ORDER BY cc.ordem, cc.id LIMIT 1), '') AS portfolio,
                (SELECT MAX(pc.valor_numero)
                 FROM producao_campos pc
                 JOIN carteira_colunas cc ON cc.id = pc.coluna_id
                 WHERE pc.producao_id = pr.id
                   AND UPPER(cc.chave) IN ({dynamic_keys})
                ) AS dynamic_honorarios
            FROM producao_registros pr
            LEFT JOIN users u ON u.id = pr.user_id
            LEFT JOIN user_monthly_goals umg
              ON umg.user_id = pr.user_id AND umg.competencia = pr.competencia
            LEFT JOIN producao_gamma gamma ON gamma.producao_id = pr.id
            LEFT JOIN producao_gamma_gerencial bg ON bg.producao_id = pr.id
            LEFT JOIN producao_alpha it ON it.producao_id = pr.id
            LEFT JOIN producao_beta rt ON rt.producao_id = pr.id
            LEFT JOIN carteiras_negociais c ON UPPER(c.slug) = UPPER(pr.carteira)
            WHERE {' AND '.join(clauses)}
            ORDER BY pr.data_acordo, pr.updated_at, pr.id
        """
        with self._connection() as conn:
            return [dict(row) for row in conn.execute(sql, tuple(params)).fetchall()]

    def _append_record_filters(
        self,
        clauses: list[str],
        params: list[Any],
        filters: dict[str, Any],
        table_alias: str,
        placeholder: str | None = None,
    ) -> None:
        p = placeholder or ("%s" if self.negocial.database_backend == "postgresql" else "?")
        column = lambda name: f"{table_alias}{name}"
        if filters.get("wallet"):
            clauses.append(f"UPPER({column('carteira')}) = {p}")
            params.append(filters["wallet"])
        if filters.get("status"):
            clauses.append(f"UPPER({column('status')}) = {p}")
            params.append(filters["status"])
        if filters.get("agreement_type"):
            clauses.append(f"UPPER({column('tipo_acordo')}) = {p}")
            params.append(filters["agreement_type"])
        if filters.get("negotiator"):
            clauses.append(f"{column('user_id')} IN (SELECT id FROM users WHERE LOWER(username) = LOWER({p}))")
            params.append(filters["negotiator"])

    def _connection(self):
        if self.negocial.database_backend == "postgresql":
            return self.negocial._connect_postgres()
        return self.negocial.connect()

    def _build_payload(
        self,
        rows: list[dict[str, Any]],
        previous_rows: list[dict[str, Any]],
        comparison_rows: list[dict[str, Any]],
        filters: dict[str, Any],
        version: str,
    ) -> dict[str, Any]:
        summary = self._summary(rows, filters)
        previous = self._summary(previous_rows, filters)
        summary["comparison"] = {
            "agreements": self._delta(summary["agreements"], previous["agreements"]),
            "total_value": self._delta(summary["total_value"], previous["total_value"]),
            "paid_honorarios": self._delta(summary["paid_honorarios"], previous["paid_honorarios"]),
            "conversion_rate": round(summary["conversion_rate"] - previous["conversion_rate"], 2),
        }
        return {
            "name": "Inteligencia de Producao",
            "version": version,
            "generated_at": datetime.now().isoformat(timespec="seconds"),
            "period": self._period_metadata(filters, rows),
            "filters": filters,
            "options": self._filter_options(),
            "summary": summary,
            "comparisons": self._comparisons(comparison_rows, filters["year"]),
            "daily": self._trend(rows, filters),
            "status": self._status(rows),
            "negotiators": self._negotiators(rows),
            "wallets": self._wallets(rows),
            "wallet_analysis": self._wallet_analysis(rows, filters),
            "pipeline": self._pipeline(rows),
            "quality": self._quality(rows),
        }

    def _summary(self, rows: list[dict[str, Any]], filters: dict[str, Any]) -> dict[str, Any]:
        total_value = sum(self._number(row.get("valor_total_acordo")) for row in rows)
        paid = [row for row in rows if self._status_key(row) == "PAGAMENTO_REALIZADO"]
        awaiting = [row for row in rows if self._status_key(row) == "AGUARDANDO_PAGAMENTO"]
        paid_value = sum(self._number(row.get("valor_total_acordo")) for row in paid)
        paid_honorarios = sum(self._honorarios(row) for row in paid)
        projected_honorarios = sum(self._honorarios(row) for row in rows if self._status_key(row) not in {"QUEBRA", "PROPOSTA_NEGADA", "OPERACAO_RECOMPRADA"})
        awaiting_honorarios = sum(self._honorarios(row) for row in awaiting)
        unique_goals: dict[tuple[str, str], float] = {}
        for row in rows:
            competence = self._date_text(row.get("competencia"))[:7]
            goal_key = (
                str(row.get("username") or ""),
                competence if filters.get("period_scope") in {"journey", "year"} else "",
            )
            unique_goals[goal_key] = self._number(row.get("meta_pagamento"))
        goal = sum(unique_goals.values())
        agreements = len(rows)
        conversion = self._conversion_rate(rows)
        scope = filters.get("period_scope")
        if scope == "journey":
            forecast = paid_honorarios
        elif scope == "year":
            today = date.today()
            if filters["year"] == today.year:
                days = 366 if calendar.isleap(today.year) else 365
                forecast = paid_honorarios / max(1, today.timetuple().tm_yday) * days
            else:
                forecast = paid_honorarios
        else:
            days = calendar.monthrange(filters["year"], filters["month"])[1]
            today = date.today()
            elapsed = today.day if today.year == filters["year"] and today.month == filters["month"] else days
            forecast = paid_honorarios / max(1, elapsed) * days
        return {
            "agreements": agreements,
            "total_value": round(total_value, 2),
            "paid_count": len(paid),
            "paid_value": round(paid_value, 2),
            "paid_honorarios": round(paid_honorarios, 2),
            "projected_honorarios": round(projected_honorarios, 2),
            "awaiting_count": len(awaiting),
            "awaiting_honorarios": round(awaiting_honorarios, 2),
            "average_ticket": round(total_value / agreements, 2) if agreements else 0,
            "conversion_rate": round(conversion, 2),
            "goal": round(goal, 2),
            "goal_percent": round(paid_honorarios / goal * 100, 2) if goal else 0,
            "forecast": round(forecast, 2),
            "last_update": max((self._datetime_text(row.get("updated_at")) for row in rows), default=""),
        }

    def _daily(self, rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
        grouped: dict[str, dict[str, Any]] = {}
        for row in rows:
            agreement_date = self._metric_reference_date(row, "total_value")
            if agreement_date:
                day = agreement_date.isoformat()
                item = grouped.setdefault(day, self._trend_bucket(day))
                self._accumulate_production_trend_bucket(item, row)

            if self._status_key(row) == "PAGAMENTO_REALIZADO":
                payment_date = self._metric_reference_date(row, "paid_honorarios")
                if payment_date:
                    day = payment_date.isoformat()
                    item = grouped.setdefault(day, self._trend_bucket(day))
                    self._accumulate_payment_trend_bucket(item, row)
        result = []
        cumulative = 0.0
        for key in sorted(grouped):
            item = grouped[key]
            cumulative += item["paid_honorarios"]
            self._round_trend_bucket(item)
            item["cumulative_honorarios"] = round(cumulative, 2)
            result.append(item)
        return result

    def _trend(self, rows: list[dict[str, Any]], filters: dict[str, Any]) -> list[dict[str, Any]]:
        scope = filters.get("period_scope")
        if scope == "month":
            return self._daily(rows)
        grouped: dict[str, dict[str, Any]] = {}
        for row in rows:
            competence = self._as_date(row.get("competencia")) or self._as_date(row.get("data_acordo"))
            if not competence:
                continue
            key = f"{competence.year:04d}-{competence.month:02d}"
            item = grouped.setdefault(
                key,
                self._trend_bucket(f"{key}-01"),
            )
            self._accumulate_trend_bucket(item, row)

        if scope == "year":
            year, month = filters["year"], 1
            final_year, final_month = filters["year"], 12
        else:
            if not grouped:
                return []
            first_key = min(grouped)
            year, month = (int(part) for part in first_key.split("-"))
            today = date.today()
            final_year, final_month = today.year, today.month
        result = []
        cumulative = 0.0
        while (year, month) <= (final_year, final_month):
            key = f"{year:04d}-{month:02d}"
            item = grouped.get(
                key,
                self._trend_bucket(f"{key}-01"),
            )
            cumulative += item["paid_honorarios"]
            self._round_trend_bucket(item)
            item["cumulative_honorarios"] = round(cumulative, 2)
            result.append(item)
            year, month = (year + 1, 1) if month == 12 else (year, month + 1)
        return result

    def _trend_bucket(self, reference: str) -> dict[str, Any]:
        return {
            "date": reference,
            "agreements": 0,
            "value": 0.0,
            "total_value": 0.0,
            "paid": 0,
            "paid_honorarios": 0.0,
            "paid_value": 0.0,
            "cash_value": 0.0,
            "installment_total": 0.0,
            "breaks_value": 0.0,
            "negated_value": 0.0,
        }

    def _accumulate_trend_bucket(self, item: dict[str, Any], row: dict[str, Any]) -> None:
        self._accumulate_production_trend_bucket(item, row)
        if self._status_key(row) == "PAGAMENTO_REALIZADO":
            self._accumulate_payment_trend_bucket(item, row)

    def _accumulate_production_trend_bucket(self, item: dict[str, Any], row: dict[str, Any]) -> None:
        total_value = self._number(row.get("valor_total_acordo"))
        status = self._status_key(row)
        agreement_type = self._agreement_type(row)
        item["agreements"] += 1
        item["value"] += total_value
        item["total_value"] += total_value
        if agreement_type == "A_VISTA":
            item["cash_value"] += total_value
        if agreement_type == "PARCELADO":
            item["installment_total"] += total_value
        if status == "QUEBRA":
            item["breaks_value"] += total_value
        if status == "PROPOSTA_NEGADA":
            item["negated_value"] += total_value

    def _accumulate_payment_trend_bucket(self, item: dict[str, Any], row: dict[str, Any]) -> None:
        item["paid"] += 1
        item["paid_honorarios"] += self._honorarios(row)
        item["paid_value"] += self._number(row.get("valor_total_acordo"))

    def _metric_reference_date(
        self,
        row: dict[str, Any],
        metric: str,
        monthly: bool = False,
    ) -> date | None:
        if metric in {"paid_honorarios", "paid_value"}:
            payment_date = self._as_date(row.get("data_pagamento"))
            if payment_date:
                return payment_date
        if monthly:
            return self._as_date(row.get("competencia")) or self._as_date(row.get("data_acordo"))
        return self._as_date(row.get("data_acordo"))

    def _round_trend_bucket(self, item: dict[str, Any]) -> None:
        for field in (
            "value",
            "total_value",
            "paid_honorarios",
            "paid_value",
            "cash_value",
            "installment_total",
            "breaks_value",
            "negated_value",
        ):
            item[field] = round(item[field], 2)

    def _period_metadata(self, filters: dict[str, Any], rows: list[dict[str, Any]]) -> dict[str, Any]:
        if filters.get("period_scope") == "month":
            return {
                "scope": "month",
                "month": filters["month"],
                "year": filters["year"],
                "label": f"{self._month_name(filters['month'])} de {filters['year']}",
                "granularity": "day",
            }
        if filters.get("period_scope") == "year":
            return {
                "scope": "year",
                "year": filters["year"],
                "label": f"Ano de {filters['year']}",
                "granularity": "month",
            }
        dates = [
            parsed
            for row in rows
            if (parsed := (self._as_date(row.get("competencia")) or self._as_date(row.get("data_acordo"))))
        ]
        today = date.today()
        first = min(dates) if dates else today
        return {
            "scope": "journey",
            "start": f"{first.year:04d}-{first.month:02d}-01",
            "end": f"{today.year:04d}-{today.month:02d}-01",
            "label": f"{self._month_name(first.month)} de {first.year} ate {self._month_name(today.month)} de {today.year}",
            "granularity": "month",
        }

    def _comparisons(self, rows: list[dict[str, Any]], selected_year: int) -> dict[str, Any]:
        by_year: dict[int, list[dict[str, Any]]] = defaultdict(list)
        by_month: dict[tuple[int, int], list[dict[str, Any]]] = defaultdict(list)
        for row in rows:
            competence = self._as_date(row.get("competencia")) or self._as_date(row.get("data_acordo"))
            if not competence:
                continue
            by_year[competence.year].append(row)
            by_month[(competence.year, competence.month)].append(row)

        years = sorted(set(by_year) | {selected_year - 1, selected_year})
        annual = [
            {"year": year, **self._comparison_metrics(by_year.get(year, []))}
            for year in years
        ]
        monthly = [
            {
                "month": month,
                "label": self._month_name(month),
                "previous": self._comparison_metrics(by_month.get((selected_year - 1, month), [])),
                "current": self._comparison_metrics(by_month.get((selected_year, month), [])),
                "years": {
                    str(year): self._comparison_metrics(by_month.get((year, month), []))
                    for year in years
                },
            }
            for month in range(1, 13)
        ]
        return {
            "selected_year": selected_year,
            "previous_year": selected_year - 1,
            "years": years,
            "annual": annual,
            "monthly": monthly,
        }

    def _comparison_metrics(self, rows: list[dict[str, Any]]) -> dict[str, Any]:
        bucket = self._trend_bucket("")
        for row in rows:
            self._accumulate_trend_bucket(bucket, row)
        self._round_trend_bucket(bucket)
        return {
            "agreements": bucket["agreements"],
            "paid_count": sum(1 for row in rows if self._status_key(row) == "PAGAMENTO_REALIZADO"),
            "breaks_count": sum(1 for row in rows if self._status_key(row) == "QUEBRA"),
            "total_value": bucket["total_value"],
            "paid_honorarios": bucket["paid_honorarios"],
            "paid_value": bucket["paid_value"],
            "cash_value": bucket["cash_value"],
            "installment_total": bucket["installment_total"],
            "breaks_value": bucket["breaks_value"],
            "negated_value": bucket["negated_value"],
            "conversion_rate": self._conversion_rate(rows),
        }

    def _status(self, rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
        grouped: dict[str, dict[str, Any]] = {}
        for row in rows:
            key = self._status_key(row) or "SEM_STATUS"
            item = grouped.setdefault(key, {"key": key, "label": self.STATUS_LABELS.get(key, key.replace("_", " ").title()), "count": 0, "value": 0.0, "honorarios": 0.0})
            item["count"] += 1
            item["value"] += self._number(row.get("valor_total_acordo"))
            item["honorarios"] += self._honorarios(row)
        total = len(rows)
        result = []
        for item in grouped.values():
            item["value"] = round(item["value"], 2)
            item["honorarios"] = round(item["honorarios"], 2)
            item["share"] = round(item["count"] / total * 100, 2) if total else 0
            result.append(item)
        return sorted(result, key=lambda item: item["count"], reverse=True)

    def _negotiators(self, rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
        grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for row in rows:
            grouped[str(row.get("username") or "Nao identificado")].append(row)
        result = []
        for username, items in grouped.items():
            paid = [row for row in items if self._status_key(row) == "PAGAMENTO_REALIZADO"]
            total = sum(self._number(row.get("valor_total_acordo")) for row in items)
            paid_honorarios = sum(self._honorarios(row) for row in paid)
            monthly_goals = {
                self._date_text(row.get("competencia"))[:7]: self._number(row.get("meta_pagamento"))
                for row in items
                if row.get("competencia")
            }
            goal = sum(monthly_goals.values()) if monthly_goals else 0
            result.append({
                "username": username,
                "wallet": str(items[0].get("carteira") or ""),
                "agreements": len(items),
                "total_value": round(total, 2),
                "paid_count": len(paid),
                "paid_honorarios": round(paid_honorarios, 2),
                "goal": round(goal, 2),
                "goal_percent": round(paid_honorarios / goal * 100, 2) if goal else 0,
                "conversion_rate": self._conversion_rate(items),
                "average_ticket": round(total / len(items), 2) if items else 0,
                "breaks": sum(1 for row in items if self._status_key(row) == "QUEBRA"),
                "negated": sum(1 for row in items if self._status_key(row) == "PROPOSTA_NEGADA"),
                "last_update": max((self._datetime_text(row.get("updated_at")) for row in items), default=""),
            })
        return sorted(result, key=lambda item: (item["paid_honorarios"], item["total_value"]), reverse=True)

    def _negotiator_agreements(self, rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
        agreements = []
        for row in rows:
            agreements.append({
                "id": row.get("id"),
                "client": str(row.get("cliente") or "Cliente nao identificado"),
                "identifier": str(row.get("identifier") or "Nao informado"),
                "negotiator": str(row.get("username") or "Nao identificado"),
                "status": self._status_key(row),
                "status_label": self.STATUS_DETAIL_LABELS.get(
                    self._status_key(row),
                    self._status_key(row).replace("_", " ").title(),
                ),
                "agreement_value": round(self._number(row.get("valor_total_acordo")), 2),
                "received_honorarios": round(self._honorarios(row), 2),
            })
        return sorted(
            agreements,
            key=lambda item: (item["agreement_value"], item["received_honorarios"], item["client"]),
            reverse=True,
        )

    def _wallets(self, rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
        grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for row in rows:
            grouped[str(row.get("carteira") or "Nao identificada")].append(row)
        total_value_all = sum(self._number(row.get("valor_total_acordo")) for row in rows)
        result = []
        for wallet, items in grouped.items():
            total = sum(self._number(row.get("valor_total_acordo")) for row in items)
            paid = [row for row in items if self._status_key(row) == "PAGAMENTO_REALIZADO"]
            result.append({
                "wallet": wallet,
                "agreements": len(items),
                "total_value": round(total, 2),
                "paid_count": len(paid),
                "paid_honorarios": round(sum(self._honorarios(row) for row in paid), 2),
                "conversion_rate": self._conversion_rate(items),
                "breaks": sum(1 for row in items if self._status_key(row) == "QUEBRA"),
                "average_ticket": round(total / len(items), 2) if items else 0,
                "share": round(total / total_value_all * 100, 2) if total_value_all else 0,
            })
        return sorted(result, key=lambda item: item["total_value"], reverse=True)

    def _wallet_analysis(
        self,
        rows: list[dict[str, Any]],
        filters: dict[str, Any],
    ) -> list[dict[str, Any]]:
        grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for row in rows:
            grouped[str(row.get("carteira") or "NAO_IDENTIFICADA").upper()].append(row)

        alpha_goals = (
            self._alpha_portfolio_goals(filters)
            if "ALPHA" in grouped
            else {}
        )
        result = []
        for wallet, items in grouped.items():
            paid = [row for row in items if self._status_key(row) == "PAGAMENTO_REALIZADO"]
            valid_projection = [
                row for row in items
                if self._status_key(row) not in {"QUEBRA", "PROPOSTA_NEGADA", "OPERACAO_RECOMPRADA"}
            ]
            cash = [row for row in items if self._agreement_type(row) == "A_VISTA"]
            installments = [row for row in items if self._agreement_type(row) == "PARCELADO"]
            total_value = sum(self._number(row.get("valor_total_acordo")) for row in items)
            entry_value = sum(self._number(row.get("valor_entrada")) for row in items)
            paid_honorarios = sum(self._honorarios(row) for row in paid)
            projected_honorarios = sum(self._honorarios(row) for row in valid_projection)
            expected_honorarios = (
                sum(self._number(row.get("valor_total_acordo")) * 0.10 for row in valid_projection)
                if wallet == "GAMMA"
                else projected_honorarios
            )
            awaiting_honorarios = sum(
                self._honorarios(row)
                for row in items
                if self._status_key(row) == "AGUARDANDO_PAGAMENTO"
            )
            valid_projection_total = sum(
                self._number(row.get("valor_total_acordo"))
                for row in valid_projection
            )

            result.append({
                "wallet": wallet,
                "agreements": len(items),
                "total_value": round(total_value, 2),
                "entry_value": round(entry_value, 2),
                "cash_count": len(cash),
                "cash_value": round(sum(self._number(row.get("valor_total_acordo")) for row in cash), 2),
                "installment_count": len(installments),
                "installment_total": round(
                    sum(self._number(row.get("valor_total_acordo")) for row in installments),
                    2,
                ),
                "installment_entry": round(
                    sum(self._number(row.get("valor_entrada")) for row in installments),
                    2,
                ),
                "paid_count": len(paid),
                "paid_value": round(
                    sum(self._number(row.get("valor_total_acordo")) for row in paid),
                    2,
                ),
                "paid_honorarios": round(paid_honorarios, 2),
                "projected_honorarios": round(projected_honorarios, 2),
                "honorarios": {
                    "expected": round(expected_honorarios, 2),
                    "flexibilized": round(projected_honorarios, 2),
                    "received": round(paid_honorarios, 2),
                    "awaiting": round(awaiting_honorarios, 2),
                    "difference": round(expected_honorarios - projected_honorarios, 2),
                    "effective_percent": round(
                        projected_honorarios / valid_projection_total * 100,
                        2,
                    ) if valid_projection_total else 0,
                },
                "conversion_rate": self._conversion_rate(items),
                "average_ticket": round(total_value / len(items), 2) if items else 0,
                "breaks": sum(1 for row in items if self._status_key(row) == "QUEBRA"),
                "negated": sum(1 for row in items if self._status_key(row) == "PROPOSTA_NEGADA"),
                "last_update": max(
                    (self._datetime_text(row.get("updated_at")) for row in items),
                    default="",
                ),
                "trend": self._wallet_trend(items, filters, wallet),
                "portfolios": self._wallet_portfolios(
                    items,
                    wallet,
                    alpha_goals if wallet == "ALPHA" else {},
                ),
                "negotiators": self._negotiators(items)[:10],
                "funnel": self._wallet_funnel(items),
                "gecors": self._wallet_dimension(items, "gecor"),
                "states": self._wallet_dimension(items, "uf"),
            })
        return sorted(result, key=lambda item: item["total_value"], reverse=True)

    def _wallet_funnel(self, rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
        stages = (
            ("PROPOSTA", "Propostas"),
            ("AGUARDANDO_PAGAMENTO", "Aguardando pagamento"),
            ("PAGAMENTO_REALIZADO", "Pagamentos realizados"),
            ("QUEBRA", "Quebras"),
        )
        result = []
        for key, label in stages:
            items = [row for row in rows if self._status_key(row) == key]
            result.append({
                "key": key,
                "label": label,
                "count": len(items),
                "total_value": round(
                    sum(self._number(row.get("valor_total_acordo")) for row in items),
                    2,
                ),
                "honorarios": round(sum(self._honorarios(row) for row in items), 2),
            })
        return result

    def _wallet_dimension(
        self,
        rows: list[dict[str, Any]],
        field: str,
    ) -> list[dict[str, Any]]:
        grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for row in rows:
            value = str(row.get(field) or "Nao informado").strip() or "Nao informado"
            grouped[value.upper()].append(row)
        result = []
        total_value_all = sum(self._number(row.get("valor_total_acordo")) for row in rows)
        for value, items in grouped.items():
            paid = [row for row in items if self._status_key(row) == "PAGAMENTO_REALIZADO"]
            total_value = sum(self._number(row.get("valor_total_acordo")) for row in items)
            result.append({
                "value": value,
                "agreements": len(items),
                "total_value": round(total_value, 2),
                "entry_value": round(sum(self._number(row.get("valor_entrada")) for row in items), 2),
                "paid_honorarios": round(sum(self._honorarios(row) for row in paid), 2),
                "conversion_rate": self._conversion_rate(items),
                "share": round(total_value / total_value_all * 100, 2) if total_value_all else 0,
            })
        return sorted(
            result,
            key=lambda item: (item["total_value"], item["agreements"]),
            reverse=True,
        )

    def _wallet_trend(
        self,
        rows: list[dict[str, Any]],
        filters: dict[str, Any],
        wallet: str,
    ) -> list[dict[str, Any]]:
        grouped: dict[str, dict[str, Any]] = {}
        journey = filters.get("period_scope") == "journey"

        def bucket(reference: date) -> dict[str, Any]:
            key = (
                f"{reference.year:04d}-{reference.month:02d}"
                if journey
                else reference.isoformat()
            )
            return grouped.setdefault(key, {
                "date": f"{key}-01" if journey else key,
                "agreements": 0,
                "paid": 0,
                "total_value": 0.0,
                "entry_value": 0.0,
                "base_value": 0.0,
                "paid_honorarios": 0.0,
                "paid_value": 0.0,
                "cash_value": 0.0,
                "installment_total": 0.0,
                "breaks_value": 0.0,
                "negated_value": 0.0,
            })

        for row in rows:
            reference = self._metric_reference_date(row, "total_value", monthly=journey)
            if reference:
                item = bucket(reference)
                item["agreements"] += 1
                item["total_value"] += self._number(row.get("valor_total_acordo"))
                item["entry_value"] += self._number(row.get("valor_entrada"))
                item["base_value"] += self._wallet_base_value(row, wallet)
                status = self._status_key(row)
                agreement_type = self._agreement_type(row)
                total_value = self._number(row.get("valor_total_acordo"))
                if agreement_type == "A_VISTA":
                    item["cash_value"] += total_value
                if agreement_type == "PARCELADO":
                    item["installment_total"] += total_value
                if status == "QUEBRA":
                    item["breaks_value"] += total_value
                if status == "PROPOSTA_NEGADA":
                    item["negated_value"] += total_value

            if self._status_key(row) == "PAGAMENTO_REALIZADO":
                payment_reference = self._metric_reference_date(row, "paid_honorarios", monthly=journey)
                if payment_reference:
                    payment_item = bucket(payment_reference)
                    payment_item["paid"] += 1
                    payment_item["paid_honorarios"] += self._honorarios(row)
                    payment_item["paid_value"] += self._number(row.get("valor_total_acordo"))
        result = []
        for key in sorted(grouped):
            item = grouped[key]
            for field in (
                "total_value",
                "entry_value",
                "base_value",
                "paid_honorarios",
                "paid_value",
                "cash_value",
                "installment_total",
                "breaks_value",
                "negated_value",
            ):
                item[field] = round(item[field], 2)
            result.append(item)
        return result

    def _wallet_portfolios(
        self,
        rows: list[dict[str, Any]],
        wallet: str,
        goals: dict[str, dict[str, Any]],
    ) -> list[dict[str, Any]]:
        grouped: dict[str, dict[str, Any]] = {}
        for row in rows:
            portfolio = str(row.get("portfolio") or "Nao informado").strip() or "Nao informado"
            key = self._portfolio_key(portfolio)
            item = grouped.setdefault(key, {
                "portfolio": portfolio,
                "portfolio_key": key,
                "agreements": 0,
                "total_value": 0.0,
                "entry_value": 0.0,
                "base_value": 0.0,
                "paid_honorarios": 0.0,
            })
            item["agreements"] += 1
            item["total_value"] += self._number(row.get("valor_total_acordo"))
            item["entry_value"] += self._number(row.get("valor_entrada"))
            item["base_value"] += self._wallet_base_value(row, wallet)
            if self._status_key(row) == "PAGAMENTO_REALIZADO":
                item["paid_honorarios"] += self._honorarios(row)

        total_base = sum(item["base_value"] for item in grouped.values())
        result = []
        for key, item in grouped.items():
            goal = goals.get(key, {})
            goal_value = self._number(goal.get("goal"))
            item.update({
                "total_value": round(item["total_value"], 2),
                "entry_value": round(item["entry_value"], 2),
                "base_value": round(item["base_value"], 2),
                "paid_honorarios": round(item["paid_honorarios"], 2),
                "goal": round(goal_value, 2),
                "goal_attainment": round(item["base_value"] / goal_value * 100, 2) if goal_value else 0,
                "share": round(item["base_value"] / total_base * 100, 2) if total_base else 0,
                "goal_source": goal.get("source") or "",
            })
            result.append(item)
        return sorted(result, key=lambda item: (item["base_value"], item["total_value"]), reverse=True)

    def _alpha_portfolio_goals(self, filters: dict[str, Any]) -> dict[str, dict[str, Any]]:
        start, end = self._selected_period_bounds(filters)
        placeholder = "%s" if self.negocial.database_backend == "postgresql" else "?"
        try:
            with self._connection() as conn:
                rows = conn.execute(
                    f"""
                    SELECT
                        portfolio,
                        portfolio_key,
                        meta_pnt,
                        source_type
                    FROM alpha_portfolio_goals
                    WHERE active = TRUE
                      AND competence >= {placeholder}
                      AND competence < {placeholder}
                    """,
                    (start, end),
                ).fetchall()
        except Exception:
            return {}
        result: dict[str, dict[str, Any]] = {}
        for row in rows:
            item = dict(row)
            key = self._portfolio_key(item.get("portfolio_key") or item.get("portfolio"))
            current = result.setdefault(key, {"goal": 0.0, "sources": set()})
            current["goal"] += self._number(item.get("meta_pnt"))
            if item.get("source_type"):
                current["sources"].add(str(item["source_type"]))
        for item in result.values():
            item["goal"] = round(item["goal"], 2)
            item["source"] = ", ".join(sorted(item.pop("sources")))
        return result

    def _wallet_base_value(self, row: dict[str, Any], wallet: str) -> float:
        total = self._number(row.get("valor_total_acordo"))
        entry = self._number(row.get("valor_entrada"))
        if wallet in {"ALPHA", "BETA"} and self._agreement_type(row) == "PARCELADO":
            return entry
        return total

    def _agreement_type(self, row: dict[str, Any]) -> str:
        value = str(row.get("tipo_acordo") or "").strip().upper().replace(" ", "_")
        return "A_VISTA" if value in {"A_VISTA", "AVISTA", "A-VISTA"} else value

    def _portfolio_key(self, value: Any) -> str:
        text = unicodedata.normalize("NFKD", str(value or ""))
        return "".join(char for char in text if char.isalnum()).upper() or "NAO_INFORMADO"

    def _pipeline(self, rows: list[dict[str, Any]]) -> dict[str, Any]:
        today = date.today()
        overdue: list[dict[str, Any]] = []
        due_soon: list[dict[str, Any]] = []
        stagnant: list[dict[str, Any]] = []
        for row in rows:
            status = self._status_key(row)
            if status not in self.OPEN_STATUSES:
                continue
            due = self._as_date(row.get("data_vencimento"))
            updated = self._as_datetime(row.get("updated_at"))
            item = self._risk_item(row)
            if due and due < today:
                item["days"] = (today - due).days
                overdue.append(item)
            elif due and 0 <= (due - today).days <= 5:
                item["days"] = (due - today).days
                due_soon.append(item)
            if updated and (datetime.now(updated.tzinfo) - updated).days >= 7:
                item = self._risk_item(row)
                item["days"] = (datetime.now(updated.tzinfo) - updated).days
                stagnant.append(item)
        key = lambda item: (item.get("days", 0), item.get("value", 0))
        return {
            "overdue": sorted(overdue, key=key, reverse=True)[:40],
            "due_soon": sorted(due_soon, key=lambda item: item.get("days", 0))[:40],
            "stagnant": sorted(stagnant, key=key, reverse=True)[:40],
            "counts": {"overdue": len(overdue), "due_soon": len(due_soon), "stagnant": len(stagnant)},
        }

    def _quality(self, rows: list[dict[str, Any]]) -> dict[str, Any]:
        missing_client = sum(1 for row in rows if not str(row.get("cliente") or "").strip())
        missing_identifier = sum(1 for row in rows if not str(row.get("identifier") or "").strip())
        zero_value = sum(1 for row in rows if self._number(row.get("valor_total_acordo")) <= 0)
        identifiers: dict[tuple[str, str], int] = defaultdict(int)
        for row in rows:
            identifier = str(row.get("identifier") or "").strip()
            if identifier:
                identifiers[(str(row.get("carteira") or ""), identifier)] += 1
        duplicates = sum(count - 1 for count in identifiers.values() if count > 1)
        issues = missing_client + missing_identifier + zero_value
        score = max(0, 100 - (issues / max(1, len(rows)) * 100))
        return {
            "score": round(score, 1),
            "missing_client": missing_client,
            "missing_identifier": missing_identifier,
            "zero_value": zero_value,
            "duplicate_occurrences": duplicates,
        }

    def _filter_options(self) -> dict[str, Any]:
        with self._connection() as conn:
            wallets = [str(row["slug"] if isinstance(row, (dict, sqlite3.Row)) else row[0]) for row in conn.execute(
                "SELECT slug FROM carteiras_negociais WHERE active = TRUE ORDER BY nome"
            ).fetchall()]
            users = [dict(row) for row in conn.execute(
                """
                SELECT username, carteira
                FROM users app_user
                WHERE app_user.active = TRUE
                   OR EXISTS (
                       SELECT 1
                       FROM producao_registros record
                       WHERE record.user_id = app_user.id
                   )
                ORDER BY username
                """
            ).fetchall()]
            years_rows = conn.execute(
                "SELECT DISTINCT EXTRACT(YEAR FROM competencia) AS year FROM producao_registros ORDER BY year DESC"
                if self.negocial.database_backend == "postgresql"
                else "SELECT DISTINCT CAST(strftime('%Y', data_acordo) AS INTEGER) AS year FROM producao_registros ORDER BY year DESC"
            ).fetchall()
        years = [int(dict(row).get("year")) for row in years_rows if dict(row).get("year")]
        if date.today().year not in years:
            years.insert(0, date.today().year)
        return {
            "wallets": wallets,
            "negotiators": users,
            "years": years,
            "statuses": [{"value": key, "label": value} for key, value in self.STATUS_LABELS.items()],
            "agreement_types": [
                {"value": "A_VISTA", "label": "A vista"},
                {"value": "PARCELADO", "label": "Parcelado"},
            ],
        }

    def _honorarios(self, row: dict[str, Any]) -> float:
        gamma_value = self._number(row.get("gamma_valor_ho"))
        # Zero is a valid received-fee value for GAMMA. It must not fall back to
        # the configured 10% rate, which is used only by non-GAMMA dynamic rows.
        if row.get("gamma_producao_id") is not None or str(row.get("carteira") or "").upper() == "GAMMA":
            return gamma_value
        dynamic = row.get("dynamic_honorarios")
        if dynamic is not None:
            return self._number(dynamic)
        if bool(row.get("usa_percentual_ho")):
            percentage = self._number(row.get("percentual_ho_padrao"))
            return self._number(row.get("valor_total_acordo")) * percentage / 100
        return 0.0

    def _risk_item(self, row: dict[str, Any]) -> dict[str, Any]:
        return {
            "id": int(row.get("id") or 0),
            "client": str(row.get("cliente") or "Cliente nao identificado"),
            "identifier": str(row.get("identifier") or ""),
            "negotiator": str(row.get("username") or "Nao identificado"),
            "wallet": str(row.get("carteira") or ""),
            "status": self._status_key(row),
            "due_date": self._date_text(row.get("data_vencimento")),
            "value": round(self._number(row.get("valor_total_acordo")), 2),
        }

    def _status_key(self, row: dict[str, Any]) -> str:
        return self._normalize_status(row.get("status"))

    def _conversion_rate(self, rows: list[dict[str, Any]]) -> float:
        paid = sum(1 for row in rows if self._status_key(row) == "PAGAMENTO_REALIZADO")
        breaks = sum(1 for row in rows if self._status_key(row) == "QUEBRA")
        concluded = paid + breaks
        return round(paid / concluded * 100, 2) if concluded else 0.0

    def _row_matches_wallet_metric(self, row: dict[str, Any], metric: str) -> bool:
        if metric == "total_value":
            return True
        if metric in {"paid_honorarios", "paid_value"}:
            return self._status_key(row) == "PAGAMENTO_REALIZADO"
        if metric == "cash_value":
            return self._agreement_type(row) == "A_VISTA"
        if metric == "installment_total":
            return self._agreement_type(row) == "PARCELADO"
        if metric == "breaks_value":
            return self._status_key(row) == "QUEBRA"
        if metric == "negated_value":
            return self._status_key(row) == "PROPOSTA_NEGADA"
        return False

    def _delta(self, current: float, previous: float) -> float | None:
        if not previous:
            return 0.0 if not current else None
        return round((current - previous) / abs(previous) * 100, 2)

    def _number(self, value: Any) -> float:
        if value in (None, ""):
            return 0.0
        if isinstance(value, (int, float, Decimal)):
            return float(value)
        text = str(value).strip().replace("R$", "").replace(" ", "")
        if "," in text:
            text = text.replace(".", "").replace(",", ".")
        try:
            return float(text)
        except ValueError:
            return 0.0

    def _as_date(self, value: Any) -> date | None:
        if isinstance(value, datetime):
            return value.date()
        if isinstance(value, date):
            return value
        try:
            return date.fromisoformat(str(value or "")[:10])
        except ValueError:
            return None

    def _as_datetime(self, value: Any) -> datetime | None:
        if isinstance(value, datetime):
            return value
        try:
            return datetime.fromisoformat(str(value or ""))
        except ValueError:
            return None

    def _date_text(self, value: Any) -> str:
        parsed = self._as_date(value)
        return parsed.isoformat() if parsed else ""

    def _datetime_text(self, value: Any) -> str:
        parsed = self._as_datetime(value)
        return parsed.isoformat(timespec="seconds") if parsed else str(value or "")

    def _month_name(self, month: int) -> str:
        return (
            "Janeiro", "Fevereiro", "Marco", "Abril", "Maio", "Junho",
            "Julho", "Agosto", "Setembro", "Outubro", "Novembro", "Dezembro",
        )[month - 1]
