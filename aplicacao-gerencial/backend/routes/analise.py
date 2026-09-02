from __future__ import annotations

from typing import Any
from urllib.parse import parse_qs


def handle_get(handler: Any, state: Any, parsed: Any, _user: dict) -> bool:
    path = parsed.path
    if path.startswith("/api/analise/defasagem"):
        return _handle_defasagem(handler, state, parsed)
    if path not in {
        "/api/analise/producao",
        "/api/analise/producao/negociador",
        "/api/analise/producao/status",
        "/api/analise/producao/dimensao",
        "/api/analise/producao/dia",
    }:
        return False
    if not handler.require_permission("monitoramento_read"):
        return True
    query = parse_qs(parsed.query)
    filters = {
        "wallet": query.get("carteira", [""])[0],
        "month": query.get("mes", [""])[0],
        "year": query.get("ano", [""])[0],
        "period_scope": query.get("periodo", [""])[0],
        "negotiator": query.get("negociador", [""])[0],
        "status": query.get("status", [""])[0],
        "agreement_type": query.get("tipo", [""])[0],
        "dimension": query.get("dimensao", [""])[0],
        "dimension_value": query.get("valor_dimensao", [""])[0],
        "selected_date": query.get("data", [""])[0],
        "metric": query.get("metrica", [""])[0],
    }
    try:
        if path == "/api/analise/producao/negociador":
            handler.json_response(state.production_analytics.negotiator_details(filters))
        elif path == "/api/analise/producao/status":
            handler.json_response(state.production_analytics.status_details(filters))
        elif path == "/api/analise/producao/dimensao":
            handler.json_response(state.production_analytics.dimension_details(filters))
        elif path == "/api/analise/producao/dia":
            handler.json_response(state.production_analytics.day_details(filters))
        else:
            handler.json_response(state.production_analytics.dashboard(filters))
    except (ValueError, RuntimeError) as exc:
        handler.error_response(str(exc), 400)
    return True


def _first(query: dict[str, list[str]], name: str, default: str = "") -> str:
    return query.get(name, [default])[0]


def _defasagem_filters(query: dict[str, list[str]]) -> dict[str, str]:
    return {
        "busca": _first(query, "busca"),
        "carteira": _first(query, "carteira"),
        "fase": _first(query, "fase"),
        "nome_op": _first(query, "nome_op"),
        "uf": _first(query, "uf"),
        "gecor": _first(query, "gecor"),
        "operador": _first(query, "operador"),
        "faixa_defasagem": _first(query, "faixa"),
        "ultimo_acionamento": _first(query, "acionamento"),
        "situacao_especial": _first(query, "situacao"),
        "filtro_operacional": _first(query, "filtro_operacional"),
        "operador_sem_retorno": _first(query, "operador_sem_retorno"),
        "tipo_defasagem": _first(query, "tipo_defasagem"),
    }


def _handle_defasagem(handler: Any, state: Any, parsed: Any) -> bool:
    if not handler.require_permission("monitoramento_read"):
        return True
    path = parsed.path
    query = parse_qs(parsed.query)
    filters = _defasagem_filters(query)
    try:
        if path == "/api/analise/defasagem/dashboard":
            handler.json_response(state.defasagem.dashboard(filters, force=_first(query, "force") == "1"))
            return True
        if path == "/api/analise/defasagem/operators":
            handler.json_response(state.defasagem.operators(filters))
            return True
        if path == "/api/analise/defasagem/records":
            handler.json_response(state.defasagem.records(
                filters,
                page=int(_first(query, "page", "1") or "1"),
                page_size=int(_first(query, "page_size", "100") or "100"),
            ))
            return True
        if path in {"/api/analise/defasagem/report.csv", "/api/analise/defasagem/report.xlsx"}:
            extension = "csv" if path.endswith(".csv") else "xlsx"
            filename, content = state.defasagem.report(
                filters,
                extension,
                snapshot_version=_first(query, "snapshot"),
            )
            if extension == "csv":
                handler.csv_response(filename, content)
            else:
                handler.file_response(filename, content, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
            return True
    except (ValueError, RuntimeError) as exc:
        handler.error_response(str(exc), 400)
        return True
    return False
