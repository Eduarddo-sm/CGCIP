from __future__ import annotations

from typing import Any

from database.repository import Repository


class SnapshotService:
    def __init__(self, repo: Repository) -> None:
        self.repo = repo
        self._table_data_cache: dict[tuple[int, str, int], dict[str, Any]] = {}
        self._month_snapshot_cache: dict[tuple[int, str, int], dict[str, Any]] = {}

    def latest_table_data(self, negociador: dict[str, Any]) -> dict[str, Any]:
        snapshot = self.repo.latest_snapshot(int(negociador["id"]), negociador["sheet"])
        if not snapshot:
            return {"headers": [], "types": {}, "rows": []}
        cache_key = (int(negociador["id"]), snapshot["sheet"], int(snapshot["id"]))
        if cache_key not in self._table_data_cache:
            self._table_data_cache[cache_key] = snapshot["content"]
        return self._table_data_cache[cache_key]

    def month_snapshot(self, negociador: dict[str, Any], month_key: str) -> dict[str, Any]:
        if not month_key or len(month_key) != 7:
            raise ValueError("Mes invalido")
        negociador_id = int(negociador["id"])
        snapshot = self.repo.latest_snapshot_for_month(negociador_id, month_key, negociador["sheet"])
        if not snapshot:
            snapshot = self.repo.latest_snapshot_for_month(negociador_id, month_key)
        if not snapshot:
            return {"snapshot": None, "data": {"headers": [], "types": {}, "rows": []}}
        cache_key = (negociador_id, month_key, int(snapshot["id"]))
        if cache_key not in self._month_snapshot_cache:
            self._month_snapshot_cache[cache_key] = {
                "snapshot": {
                    "id": snapshot["id"],
                    "sheet": snapshot["sheet"],
                    "captured_at": snapshot["captured_at"],
                },
                "data": snapshot["content"],
            }
        return self._month_snapshot_cache[cache_key]
