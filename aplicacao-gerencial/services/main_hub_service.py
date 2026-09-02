from __future__ import annotations

import hashlib
import json
from typing import Any, Callable


class MainHubService:
    def __init__(self, overview: Any, parecer: Any, protocolo: Any, dynamic_tools: Any | None = None) -> None:
        self.overview = overview
        self.parecer = parecer
        self.protocolo = protocolo
        self.dynamic_tools = dynamic_tools

    def payload(self, username: str, client_version: str = "") -> dict[str, Any]:
        errors: dict[str, str] = {}
        overview = self._safe("overview", lambda: self.overview.list_items(username, status="unread"), errors)
        pareceres = self._safe("pareceres", self.parecer.read_pendentes, errors)
        protocolos = self._safe("protocolos", self.protocolo.pending_records, errors)
        ferramentas = self._safe(
            "ferramentas",
            lambda: self.dynamic_tools.list_open_notifications(200) if self.dynamic_tools else [],
            errors,
        )
        data = {
            "overview": [item for item in overview if not item.get("lido")],
            "pareceres": pareceres,
            "protocolos": protocolos,
            "ferramentas": ferramentas,
            "errors": errors,
        }
        version = self._version(data)
        if client_version and client_version == version:
            return {"changed": False, "version": version}
        return {"changed": True, "version": version, **data}

    def _safe(self, key: str, action: Callable[[], list[dict[str, Any]]], errors: dict[str, str]) -> list[dict[str, Any]]:
        try:
            return action()
        except Exception as exc:
            errors[key] = str(exc)
            return []

    def _version(self, payload: dict[str, Any]) -> str:
        raw = json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str)
        return hashlib.sha1(raw.encode("utf-8")).hexdigest()
