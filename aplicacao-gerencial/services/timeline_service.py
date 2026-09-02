from __future__ import annotations

import hashlib
import json
from datetime import datetime
from typing import Any


class TimelineService:
    MONTHS = [
        "Janeiro",
        "Fevereiro",
        "Marco",
        "Abril",
        "Maio",
        "Junho",
        "Julho",
        "Agosto",
        "Setembro",
        "Outubro",
        "Novembro",
        "Dezembro",
    ]

    def build(self, events: list[dict[str, Any]]) -> dict[str, Any]:
        months: dict[str, dict[str, Any]] = {}
        total_changes = 0

        for event in events:
            changed_at = self._parse_datetime(event.get("changed_at"))
            if not changed_at:
                continue
            changes_count = self._changes_count(event)
            total_changes += changes_count
            month_key = changed_at.strftime("%Y-%m")
            day_key = changed_at.strftime("%Y-%m-%d")
            hour_key = changed_at.strftime("%Y-%m-%dT%H:%M:%S")

            month = months.setdefault(month_key, {
                "key": month_key,
                "date": changed_at.replace(day=1, hour=0, minute=0, second=0, microsecond=0).isoformat(),
                "label": self._month_label(changed_at),
                "changes": 0,
                "days_map": {},
            })
            month["changes"] += changes_count

            day = month["days_map"].setdefault(day_key, {
                "key": day_key,
                "date": changed_at.replace(hour=0, minute=0, second=0, microsecond=0).isoformat(),
                "label": self._day_label(changed_at),
                "changes": 0,
                "users_set": set(),
                "hours_map": {},
            })
            day["changes"] += changes_count
            day["users_set"].add(event.get("negociador_nome") or "Responsavel")

            hour = day["hours_map"].setdefault(hour_key, {
                "key": hour_key,
                "date": changed_at.isoformat(),
                "label": changed_at.strftime("%H:%M:%S"),
                "changes": 0,
                "users_set": set(),
                "events": [],
            })
            hour["changes"] += changes_count
            hour["users_set"].add(event.get("negociador_nome") or "Responsavel")
            hour["events"].append(event)

        payload = {
            "events": events,
            "months": self._finalize_months(months),
            "total_changes": total_changes,
            "version": self._version(events),
        }
        return payload

    def _finalize_months(self, months: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
        result = []
        for month in months.values():
            days = []
            for day in month.pop("days_map").values():
                hours = []
                for hour in day.pop("hours_map").values():
                    hour["users"] = sorted(hour.pop("users_set"))
                    hours.append(hour)
                day["users"] = sorted(day.pop("users_set"))
                day["hours"] = sorted(hours, key=lambda item: item["date"], reverse=True)
                days.append(day)
            month["days"] = sorted(days, key=lambda item: item["date"], reverse=True)
            result.append(month)
        return sorted(result, key=lambda item: item["date"], reverse=True)

    def _changes_count(self, event: dict[str, Any]) -> int:
        try:
            return int(event.get("changes_count") or 0)
        except (TypeError, ValueError):
            return len((event.get("delta") or {}).get("changes") or [])

    def _parse_datetime(self, value: Any) -> datetime | None:
        text = str(value or "").strip()
        if not text:
            return None
        for candidate in (text, text.replace("Z", "+00:00"), text.split(".", 1)[0]):
            try:
                return datetime.fromisoformat(candidate)
            except ValueError:
                continue
        return None

    def _month_label(self, date: datetime) -> str:
        return f"{self.MONTHS[date.month - 1]} {date.year}"

    def _day_label(self, date: datetime) -> str:
        return f"{date.day:02d} {self.MONTHS[date.month - 1][:3].upper()}"

    def _version(self, events: list[dict[str, Any]]) -> str:
        content = [
            {
                "id": event.get("id"),
                "changed_at": event.get("changed_at"),
                "changes_count": event.get("changes_count"),
            }
            for event in events
        ]
        raw = json.dumps(content, ensure_ascii=False, sort_keys=True, default=str)
        return hashlib.sha1(raw.encode("utf-8")).hexdigest()
