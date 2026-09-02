from __future__ import annotations

from typing import Any
from urllib.parse import parse_qs

from services.protocolo_service import ProtocoloError


def handle_get(handler: Any, state: Any, parsed: Any, _user: dict) -> bool:
    path = parsed.path
    if path == "/api/protocolo":
        if not handler.require_permission("protocolo_read"):
            return True
        handler.handle_protocolo(state.protocolo.records)
        return True
    if path == "/api/protocolo/pendentes":
        if not handler.require_permission("protocolo_read"):
            return True
        query = parse_qs(parsed.query)
        limit = int(query.get("limit", ["0"])[0] or "0")
        handler.handle_protocolo(lambda: state.protocolo.pending_records(limit or None))
        return True
    if path == "/api/protocolo/dashboard":
        if not handler.require_permission("protocolo_read"):
            return True
        handler.handle_protocolo(state.protocolo.dashboard)
        return True
    if path == "/api/protocolo/config":
        if not handler.require_permission("protocolo_read"):
            return True
        handler.json_response(state.protocolo.get_config())
        return True
    return False


def handle_post(handler: Any, state: Any, path: str, user: dict) -> bool:
    if path == "/api/protocolo":
        if not handler.require_permission("protocolo_read"):
            return True
        if not handler.require_permission("protocolo_write"):
            return True
        payload = handler.read_json()
        handler.handle_protocolo(lambda: state.protocolo.create(payload, user["username"]))
        return True
    if path == "/api/protocolo/status":
        if not handler.require_permission("protocolo_read"):
            return True
        if not handler.require_permission("protocolo_write"):
            return True
        payload = handler.read_json()
        handler.handle_protocolo(
            lambda: state.protocolo.update_status(
                int(payload.get("row", 0)), str(payload.get("status", "")), user["username"]
            )
        )
        return True
    if path == "/api/protocolo/cell":
        if not handler.require_permission("protocolo_read"):
            return True
        if not handler.require_permission("protocolo_write"):
            return True
        payload = handler.read_json()
        handler.handle_protocolo(
            lambda: state.protocolo.update_cell(
                int(payload.get("row", 0)), str(payload.get("header", "")), payload.get("value", ""), user["username"]
            )
        )
        return True
    return False


def handle_put(handler: Any, state: Any, path: str, _user: dict) -> bool:
    if path != "/api/protocolo/config":
        return False
    if not handler.require_permission("protocolo_write"):
        return True
    payload = handler.read_json()
    try:
        handler.json_response(state.protocolo.save_config(payload))
    except (ValueError, ProtocoloError) as exc:
        handler.error_response(str(exc), 400)
    return True




