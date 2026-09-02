from __future__ import annotations

from typing import Any
from urllib.parse import parse_qs

from services.parecer_service import ParecerError


def handle_get(handler: Any, state: Any, parsed: Any, _user: dict) -> bool:
    path = parsed.path
    actions = {
        "/api/pareceres": state.parecer.read_records,
        "/api/pareceres/pendentes": state.parecer.read_pendentes,
        "/api/pareceres/aprovacao": state.parecer.read_aprovacao_pendente,
        "/api/pareceres/aprovacao/historico": state.parecer.read_aprovacao_historico,
        "/api/dashboard": state.parecer.dashboard,
    }
    if path in actions:
        if not handler.require_permission("parecer_read"):
            return True
        handler.handle_parecer(actions[path])
        return True
    if path == "/api/pareceres/relatorio.csv":
        if not handler.require_permission("parecer_read"):
            return True
        try:
            query = parse_qs(parsed.query)
            carteira = (query.get("carteira") or [""])[0]
            filename, content = state.parecer.relatorio_csv(carteira) if carteira else state.parecer.relatorio_csv()
            handler.csv_response(filename, content)
        except ParecerError as exc:
            handler.error_response(str(exc), 400)
        except Exception:
            handler.error_response("Nao foi possivel gerar o relatorio de pareceres.", 500)
        return True
    if path == "/api/historico":
        if not handler.require_permission("parecer_read"):
            return True
        handler.json_response(state.parecer.history())
        return True
    if path == "/api/parecer/config":
        if not handler.require_permission("parecer_read"):
            return True
        handler.json_response(state.parecer.get_config())
        return True
    return False


def handle_post(handler: Any, state: Any, path: str, user: dict) -> bool:
    if path == "/api/pareceres/marcar-solicitado":
        if not handler.require_permission("parecer_read"):
            return True
        if not handler.require_permission("parecer_write"):
            return True
        payload = handler.read_json()
        pk = str(payload.get("pk", ""))
        handler.handle_parecer(lambda: handler._mark_parecer_and_notification(pk, user["username"]))
        return True
    if path in {"/api/pareceres/aprovar", "/api/pareceres/reprovar"}:
        if not handler.require_permission("approve_parecer"):
            return True
        payload = handler.read_json()
        pk = str(payload.get("pk", ""))
        reason = str(payload.get("justificativa", ""))
        descricao = str(payload.get("descricao", ""))
        action = handler._approve_parecer if path.endswith("/aprovar") else handler._reject_parecer
        handler.handle_parecer(lambda: action(pk, reason, descricao, user["username"]))
        return True
    if path == "/api/pareceres/marcar-varios":
        if not handler.require_permission("parecer_read"):
            return True
        if not handler.require_permission("parecer_write"):
            return True
        payload = handler.read_json()
        pks = list(payload.get("pks", []))
        handler.handle_parecer(lambda: handler._mark_pareceres_and_notifications(pks, user["username"]))
        return True
    if path == "/api/powerquery/atualizar":
        if not handler.require_permission("parecer_write"):
            return True
        handler.handle_parecer(lambda: handler._refresh_parecer_powerquery(user["username"]))
        return True
    return False


def handle_put(handler: Any, state: Any, path: str, _user: dict) -> bool:
    if path != "/api/parecer/config":
        return False
    if not handler.require_permission("parecer_write"):
        return True
    payload = handler.read_json()
    try:
        handler.json_response(state.parecer.save_config(payload))
    except (ValueError, ParecerError) as exc:
        handler.error_response(str(exc), 400)
    return True




