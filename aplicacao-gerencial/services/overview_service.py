from __future__ import annotations

import copy
import hashlib
import json
import threading
import time
from typing import Any

from database.repository import Repository
from services.event_log_service import EventLogService
from services.overview_builder import OverviewBuilder


class OverviewService:
    def __init__(self, repo: Repository, events: EventLogService, builder: OverviewBuilder) -> None:
        self.repo = repo
        self.events = events
        self.builder = builder
        self._cache_lock = threading.Lock()
        self._build_lock = threading.Lock()
        self._cache: dict[str, tuple[float, list[dict[str, Any]]]] = {}
        self._cache_ttl = 8

    def list_items(self, usuario: str, filters: dict[str, Any] | None = None, status: str = "unread") -> list[dict[str, Any]]:
        usuario = self._usuario(usuario)
        filters = filters or {}
        cache_key = json.dumps({"usuario": usuario, "filters": filters, "status": status}, sort_keys=True, ensure_ascii=False)
        now = time.monotonic()
        with self._cache_lock:
            cached = self._cache.get(cache_key)
            if cached and now - cached[0] < self._cache_ttl:
                return copy.deepcopy(cached[1])

        # Avoid a cache stampede when Overview, Main Hub and notifications refresh
        # together after the cache expires.
        with self._build_lock:
            now = time.monotonic()
            with self._cache_lock:
                cached = self._cache.get(cache_key)
                if cached and now - cached[0] < self._cache_ttl:
                    return copy.deepcopy(cached[1])

            events = self.events.visible_events(self.events.dedupe_events(self.repo.list_overview_events(usuario)))
            result = self.builder.build(events, filters, status)
            with self._cache_lock:
                self._cache[cache_key] = (time.monotonic(), copy.deepcopy(result))
            return result

    def payload(self, items: list[dict[str, Any]], client_version: str = "") -> dict[str, Any]:
        version = self._items_version(items)
        if client_version and client_version == version:
            return {"changed": False, "version": version, "count": len(items)}
        return {"changed": True, "version": version, "count": len(items), "items": items}

    def mark_read(self, item_id: str, usuario: str) -> dict[str, Any]:
        parts = str(item_id or "").split("_")
        if len(parts) != 3 or parts[0] not in ("ALT", "OVR"):
            raise ValueError("Item do overview invalido")
        event_id = int(parts[1])
        usuario = self._usuario(usuario)
        entries = [(event_id, int(index)) for index in parts[2].split(",")]
        marked = self.repo.mark_overview_reads(entries, usuario)
        self.clear_cache(usuario)
        return {"ok": True, "changes": marked}

    def mark_all_read(self, usuario: str, filters: dict[str, Any] | None = None) -> dict[str, Any]:
        usuario = self._usuario(usuario)
        items = self.list_items(usuario, filters, status="unread")
        entries: list[tuple[int, int]] = []
        for item in items:
            for read_index in item.get("changeIndices", [item.get("changeIndex")]):
                if read_index is None:
                    continue
                entries.append((item["eventId"], int(read_index)))
        marked = self.repo.mark_overview_reads(entries, usuario)
        self.clear_cache(usuario)
        return {"ok": True, "items": len(items), "changes": marked}

    def clear_cache(self, usuario: str | None = None) -> None:
        usuario = (usuario or "").strip()
        with self._cache_lock:
            if not usuario:
                self._cache.clear()
                return
            self._cache = {
                key: value
                for key, value in self._cache.items()
                if f'"usuario": "{usuario}"' not in key
            }

    def _items_version(self, items: list[dict[str, Any]]) -> str:
        raw = json.dumps(
            [
                {
                    "id": item.get("id"),
                    "eventId": item.get("eventId"),
                    "changeIndex": item.get("changeIndex"),
                    "dataHora": item.get("dataHora"),
                    "lido": item.get("lido"),
                    "campo": item.get("campo"),
                }
                for item in items
            ],
            ensure_ascii=False,
            sort_keys=True,
            default=str,
        )
        return hashlib.sha1(raw.encode("utf-8")).hexdigest()

    def _usuario(self, usuario: str) -> str:
        return (usuario or "Usuario Local").strip() or "Usuario Local"
