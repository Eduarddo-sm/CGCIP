from __future__ import annotations

import copy
import json
from collections.abc import Callable
from datetime import datetime
from typing import Any

from database.repository import Repository
from services.timeline_service import TimelineService


class EventLogService:
    def __init__(
        self,
        repo: Repository,
        row_values: Callable[[dict[str, Any], dict[str, Any]], dict[str, Any]],
        normalized_value: Callable[[Any], str],
        is_noop_change: Callable[[dict[str, Any]], bool],
        on_created: Callable[[], None] | None = None,
    ) -> None:
        self.repo = repo
        self.timeline = TimelineService()
        self.row_values = row_values
        self.normalized_value = normalized_value
        self.is_noop_change = is_noop_change
        self.on_created = on_created

    def payload(
        self,
        negociador_id: int,
        before_id: int | None,
        after_id: int,
        event_type: str,
        negociador: dict[str, Any],
        table: dict[str, Any],
        delta: dict[str, Any],
    ) -> dict[str, Any]:
        summary = delta["summary"]
        changes_count = summary["cells_changed"] + summary["rows_added"] + summary["rows_removed"] + summary["columns_changed"]
        if event_type == "initial_snapshot":
            changes_count = summary["rows_added"] + summary["columns_added"]
        if event_type == "new_month":
            changes_count = 1
        now = datetime.now()
        return {
            "negociador_id": negociador_id,
            "snapshot_before_id": before_id,
            "snapshot_after_id": after_id,
            "event_type": event_type,
            "sheet": table["sheet"],
            "file_path": table["file_path"],
            "changed_at": now.isoformat(timespec="seconds"),
            "changes_count": changes_count,
            "delta": delta,
            "metadata": {
                "negociador": negociador["nome"],
                "carteira": negociador.get("carteira") or "",
                "arquivo": table["file_path"],
                "sheet": table["sheet"],
                "data": now.date().isoformat(),
                "hora": now.time().isoformat(timespec="seconds"),
                "table_range": table["table_range"],
                "row_count": table["row_count"],
                "types": table["types"],
                "key_column": delta["summary"].get("key_column"),
            },
        }

    def create_once(self, payload: dict[str, Any]) -> int | None:
        if self._has_recent_duplicate_event(payload):
            return None
        event_id = self.repo.create_event(payload)
        if self.on_created:
            self.on_created()
        return event_id

    def list_events(self, negociador_id: int) -> list[dict[str, Any]]:
        return self.visible_events(self.dedupe_events(self.repo.list_events(negociador_id)))

    def build_timeline(self, negociador_id: int) -> dict[str, Any]:
        return self.timeline.build(self.list_events(negociador_id))

    def list_all_events(self, limit: int = 1500) -> list[dict[str, Any]]:
        return self.visible_events(self.dedupe_events(self.repo.list_events(None, limit=limit)))

    def get_event(self, event_id: int) -> dict[str, Any]:
        event = self.repo.get_event(event_id)
        if not event:
            raise ValueError("Evento nao encontrado")
        sanitized = self.sanitize_event_for_display(event)
        if not sanitized:
            raise ValueError("Evento sem alteracoes relevantes")
        return sanitized

    def dedupe_events(self, events: list[dict[str, Any]]) -> list[dict[str, Any]]:
        seen = set()
        deduped = []
        for event in events:
            fingerprint = self._event_display_fingerprint(event)
            if fingerprint in seen:
                continue
            seen.add(fingerprint)
            deduped.append(event)
        return deduped

    def visible_events(self, events: list[dict[str, Any]]) -> list[dict[str, Any]]:
        visible = []
        for event in events:
            sanitized = self.sanitize_event_for_display(event)
            if sanitized:
                visible.append(sanitized)
        return visible

    def sanitize_event_for_display(self, event: dict[str, Any]) -> dict[str, Any] | None:
        if event.get("event_type") == "new_month":
            return event
        # read_keys is shared by every event in an overview request and can contain
        # thousands of entries. A deep copy here multiplied that set by every event.
        payload = dict(event)
        delta = event.get("delta") or {}
        changes = [change for change in (self._sanitize_change_for_display(change, payload) for change in delta.get("changes", [])) if change]
        if not changes:
            return None
        payload["delta"] = {**delta, "changes": changes, "summary": self._display_summary(delta.get("summary", {}), changes)}
        payload["changes_count"] = len(changes)
        return payload

    def _has_recent_duplicate_event(self, payload: dict[str, Any]) -> bool:
        payload_fingerprint = self._event_fingerprint(payload)
        payload_time = datetime.fromisoformat(payload["changed_at"])
        for event in self.repo.list_events(payload["negociador_id"], limit=20):
            if self._event_fingerprint(event) != payload_fingerprint:
                continue
            event_time = datetime.fromisoformat(event["changed_at"])
            if abs((payload_time - event_time).total_seconds()) <= 90:
                return True
        return False

    def _sanitize_change_for_display(self, change: dict[str, Any], event: dict[str, Any]) -> dict[str, Any] | None:
        change_type = change.get("type")
        if change_type == "initial_snapshot":
            return None
        if self.is_noop_change(change):
            return None
        sanitized = copy.deepcopy(change)
        if change_type in {"column_added", "column_removed"}:
            count = int(sanitized.get("non_empty_values") or 0)
            description = f"{count} valor{'es' if count != 1 else ''} preenchido{'s' if count != 1 else ''}"
            sanitized["before"] = description if change_type == "column_removed" else None
            sanitized["after"] = description if change_type == "column_added" else None
        elif change_type in {"row_added", "row_removed"}:
            row_key = "after" if change_type == "row_added" else "before"
            row = self._event_row_values_for_display(sanitized.get(row_key) or {}, event)
            if not row:
                return None
            sanitized[row_key] = row
        elif change_type == "cell_changed":
            for row_key in ("row_before", "row_after"):
                row = self._event_row_values_for_display(sanitized.get(row_key) or {}, event)
                if row:
                    sanitized[row_key] = row
                else:
                    sanitized.pop(row_key, None)
        return sanitized

    def _event_row_values_for_display(self, row: dict[str, Any], event: dict[str, Any]) -> dict[str, Any]:
        values = self.row_values(row, event)
        cleaned = {
            column: value
            for column, value in values.items()
            if self.normalized_value(value)
        }
        for key in ("_row_id", "_excel_row"):
            if key in row:
                cleaned[key] = row[key]
        return cleaned

    def _display_summary(self, original: dict[str, Any], changes: list[dict[str, Any]]) -> dict[str, Any]:
        summary = dict(original or {})
        summary["cells_changed"] = len([change for change in changes if change.get("type") == "cell_changed"])
        summary["rows_added"] = len([change for change in changes if change.get("type") == "row_added"])
        summary["rows_removed"] = len([change for change in changes if change.get("type") == "row_removed"])
        summary["columns_added"] = len([change for change in changes if change.get("type") == "column_added"])
        summary["columns_removed"] = len([change for change in changes if change.get("type") == "column_removed"])
        summary["columns_changed"] = summary["columns_added"] + summary["columns_removed"]
        summary["structure_changed"] = bool(summary["columns_changed"])
        return summary

    def _event_fingerprint(self, event: dict[str, Any]) -> str:
        return json.dumps(
            {
                "negociador_id": event.get("negociador_id"),
                "event_type": event.get("event_type"),
                "sheet": event.get("sheet"),
                "changes_count": event.get("changes_count"),
                "delta": event.get("delta"),
            },
            sort_keys=True,
            ensure_ascii=False,
            default=str,
        )

    def _event_display_fingerprint(self, event: dict[str, Any]) -> str:
        metadata = event.get("metadata") or {}
        return json.dumps(
            {
                "changed_at": event.get("changed_at"),
                "event_type": event.get("event_type"),
                "sheet": event.get("sheet"),
                "file_path": event.get("file_path"),
                "negociador": metadata.get("negociador") or event.get("negociador_nome"),
                "carteira": metadata.get("carteira") or event.get("carteira"),
                "changes_count": event.get("changes_count"),
                "delta": event.get("delta"),
            },
            sort_keys=True,
            ensure_ascii=False,
            default=str,
        )
