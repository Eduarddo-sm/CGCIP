from __future__ import annotations

from typing import Any
from urllib.parse import parse_qs


def handle_get(handler: Any, state: Any, parsed: Any, user: dict) -> bool:
    if parsed.path != "/api/main-hub":
        return False
    query = parse_qs(parsed.query)
    handler.json_response(state.main_hub.payload(user["username"], query.get("version", [""])[0]))
    return True
