from __future__ import annotations

from typing import Any
from urllib.parse import parse_qs

from services.colchao_service import ColchaoError


def handle_get(handler: Any, state: Any, parsed: Any, _user: dict) -> bool:
    path = parsed.path
    query = parse_qs(parsed.query)
    profile = query.get("profile", ["alpha"])[0]
    if path == "/api/colchao/profiles":
        if not handler.require_permission("colchao_read"):
            return True
        items = []
        for carteira in state.repo.list_carteiras():
            nome = str(carteira.get("nome") or "").strip().upper()
            if not nome:
                continue
            settings = state.negocial_tools.wallet_tool_settings(nome)
            tool = next((item for item in settings.get("items", []) if item.get("key") == "colchao"), None)
            if not tool or not tool.get("enabled"):
                continue
            config = state.colchao.get_profile_config(nome)
            identifier = next(
                (
                    field for field in config.get("fields", [])
                    if field.get("enabled", True) and field.get("role") == "identifier"
                ),
                {},
            )
            items.append({
                "id": nome.lower(),
                "name": str(config.get("name") or nome).strip(),
                "description": str(carteira.get("descricao") or "").strip(),
                "keyLabel": str(identifier.get("label") or "Identificador").strip(),
                "sheets": config.get("sheet_options") or [],
            })
        handler.json_response({"items": items})
        return True
    if path == "/api/colchao/relatorio.csv":
        if not handler.require_permission("colchao_read"):
            return True
        try:
            filename, content = state.colchao.relatorio_csv(profile)
            handler.csv_response(filename, content)
        except (ColchaoError, ValueError) as exc:
            handler.error_response(str(exc), 400)
        return True
    if path == "/api/colchao":
        if not handler.require_permission("colchao_read"):
            return True
        handler.handle_colchao(lambda: state.colchao.query_records(
            page=handler._int_query(query, "page", 1),
            page_size=handler._int_query(query, "page_size", 100),
            search=query.get("search", [""])[0],
            operador=query.get("operador", [""])[0],
            status=query.get("status", [""])[0],
            vencimento=query.get("vencimento", [""])[0],
            profile=profile,
            sheet_name=query.get("sheet", [""])[0],
            all_records=query.get("all", ["0"])[0] in ("1", "true", "TRUE", "sim", "SIM"),
        ))
        return True
    if path == "/api/colchao/pendencias":
        if not handler.require_permission("colchao_read"):
            return True
        handler.handle_colchao(lambda: state.colchao.pendencias(profile))
        return True
    if path == "/api/colchao/clientes":
        if not handler.require_permission("colchao_read"):
            return True
        handler.handle_colchao(lambda: state.colchao.clients(profile, query.get("search", [""])[0]))
        return True
    if path == "/api/colchao/dashboard":
        if not handler.require_permission("colchao_read"):
            return True
        handler.handle_colchao(lambda: state.colchao.dashboard(profile))
        return True
    if path == "/api/colchao/config":
        if not handler.require_permission("colchao_read"):
            return True
        handler.json_response(state.colchao.get_profile_config(profile))
        return True
    if path == "/api/colchao/config/versions":
        if not handler.require_permission("colchao_read"):
            return True
        handler.json_response({"items": state.colchao.config_versions(profile)})
        return True
    if path == "/api/colchao/historico":
        if not handler.require_permission("colchao_read"):
            return True
        handler.json_response(state.colchao.history())
        return True
    if path == "/api/colchao/validar":
        if not handler.require_permission("colchao_read"):
            return True
        handler.handle_colchao(lambda: state.colchao.validate(profile))
        return True
    return False


def handle_post(handler: Any, state: Any, path: str, user: dict) -> bool:
    if path == "/api/colchao/status":
        if not handler.require_permission("colchao_read"):
            return True
        if not handler.require_permission("colchao_write"):
            return True
        payload = handler.read_json()
        handler.handle_colchao(lambda: handler._update_colchao_status(payload, user["username"]))
        return True
    if path == "/api/colchao/status-batch":
        if not handler.require_permission("colchao_read"):
            return True
        if not handler.require_permission("colchao_write"):
            return True
        payload = handler.read_json()
        handler.handle_colchao(lambda: handler._update_colchao_status_batch(payload, user["username"]))
        return True
    if path == "/api/colchao/vencimentos/preview":
        if not handler.require_permission("colchao_read"):
            return True
        payload = handler.read_json()
        handler.handle_colchao(lambda: state.colchao.preview_due_date_reschedule(payload, user["username"]))
        return True
    if path == "/api/colchao/vencimentos/reprogramar":
        if not handler.require_permission("colchao_read"):
            return True
        if not handler.require_permission("colchao_write"):
            return True
        payload = handler.read_json()

        def reschedule():
            result = state.colchao.reschedule_due_dates(payload, user["username"])
            state.optimizer.refresh_colchao(str(payload.get("profile") or "alpha"))
            return result

        handler.handle_colchao(reschedule)
        return True
    if path == "/api/colchao/sync":
        if not handler.require_permission("colchao_read"):
            return True
        if not handler.require_permission("colchao_write"):
            return True
        payload = handler.read_json()
        profile = str(payload.get("profile", "alpha"))
        handler.handle_colchao(lambda: handler._sync_colchao(profile))
        return True
    if path == "/api/colchao/auto-quebra":
        if not handler.require_permission("colchao_read"):
            return True
        if not handler.require_permission("colchao_write"):
            return True
        handler.handle_colchao(lambda: state.colchao.auto_break_old_agreements(user["username"]))
        return True
    if path == "/api/colchao/acordos":
        if not handler.require_permission("colchao_read"):
            return True
        if not handler.require_permission("colchao_write"):
            return True
        payload = handler.read_json()
        handler.handle_colchao(lambda: handler._create_colchao_agreement(payload, user["username"]))
        return True
    if path == "/api/colchao/abrir-planilha":
        if not handler.require_permission("colchao_read"):
            return True
        if not handler.require_permission("colchao_write"):
            return True
        payload = handler.read_json()
        profile = str(payload.get("profile", "alpha"))
        handler.handle_colchao(lambda: handler.open_local_file(state.colchao.excel_path(profile)))
        return True
    return False


def handle_put(handler: Any, state: Any, path: str, user: dict) -> bool:
    if path.startswith("/api/") and not handler.require_permission("colchao_write"):
        return True
    if path != "/api/colchao/config":
        return False
    if not handler.require_permission("colchao_write"):
        return True
    payload = handler.read_json()
    try:
        profile = str(payload.get("profile") or "alpha")
        handler.json_response(state.colchao.save_config(payload, profile=profile, usuario=user["username"]))
    except (ValueError, ColchaoError) as exc:
        handler.error_response(str(exc), 400)
    return True




