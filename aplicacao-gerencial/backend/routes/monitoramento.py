from __future__ import annotations

from typing import Any
from urllib.parse import parse_qs


def handle_get(handler: Any, state: Any, parsed: Any, _user: dict) -> bool:
    path = parsed.path
    query = parse_qs(parsed.query)
    if path == "/api/monitoramento/planilha":
        if not handler.require_permission("monitoramento_read"):
            return True
        try:
            handler.json_response(state.negocial.producao_mensal(
                query.get("carteira", [""])[0],
                int(query.get("mes", ["0"])[0] or "0"),
                int(query.get("ano", ["0"])[0] or "0"),
            ))
        except (ValueError, RuntimeError) as exc:
            handler.error_response(str(exc), 400)
        return True
    if path in {"/api/monitoramento/planilha/relatorio.csv", "/api/monitoramento/planilha/relatorio.xlsx", "/api/monitoramento/planilha/relatorio.pdf"}:
        if not handler.require_permission("monitoramento_read"):
            return True
        filters = {
            "carteira": query.get("carteira", [""])[0],
            "mes": query.get("mes", [""])[0],
            "ano": query.get("ano", [""])[0],
            "usuario": query.get("usuario", [""])[0],
            "dia": query.get("dia", [""])[0],
            "status": query.get("status", [""])[0],
            "status_label": query.get("status_label", [""])[0],
            "titulo": query.get("titulo", [""])[0],
            "observacoes": query.get("observacoes", [""])[0],
            "agrupar_por": query.get("agrupar_por", ["negociador"])[0],
            "ordenacao": query.get("ordenacao", ["valor_desc"])[0],
            "orientacao": query.get("orientacao", ["paisagem"])[0],
            "campos": query.get("campos", [""])[0],
            "quebrar_grupo": query.get("quebrar_grupo", [""])[0] in {"1", "true", "sim"},
        }
        try:
            if path.endswith(".pdf"):
                filename, content = state.negocial.producao_mensal_pdf(filters)
                handler.file_response(filename, content, "application/pdf")
            elif path.endswith(".csv"):
                filename, content = state.negocial.producao_mensal_csv(filters)
                handler.csv_response(filename, content)
            else:
                filename, content = state.negocial.producao_mensal_xlsx(filters)
                handler.file_response(filename, content, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
        except (ValueError, RuntimeError) as exc:
            handler.error_response(str(exc), 400)
        return True
    if path == "/api/monitoramento/fechamento":
        if not handler.require_permission("monitoramento_read"):
            return True
        try:
            handler.json_response(state.negocial.monthly_closing_status(
                query.get("carteira", [""])[0],
                int(query.get("mes", ["0"])[0] or "0"),
                int(query.get("ano", ["0"])[0] or "0"),
            ))
        except (ValueError, RuntimeError) as exc:
            handler.error_response(str(exc), 400)
        return True
    if path == "/api/monitoramento/fechamento/relatorio.xlsx":
        if not handler.require_permission("monitoramento_read"):
            return True
        try:
            filename, content = state.negocial.monthly_closing_report_xlsx(
                query.get("carteira", [""])[0],
                int(query.get("mes", ["0"])[0] or "0"),
                int(query.get("ano", ["0"])[0] or "0"),
            )
            handler.file_response(filename, content, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
        except (ValueError, RuntimeError) as exc:
            handler.error_response(str(exc), 400)
        return True
    return False




