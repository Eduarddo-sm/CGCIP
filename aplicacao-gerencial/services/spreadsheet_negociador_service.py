from __future__ import annotations

import os
from collections.abc import Callable
from typing import Any

from database.repository import Repository
from services.diff_service import DiffService
from services.event_log_service import EventLogService
from services.excel_reader import ExcelReader


class SpreadsheetNegotiadorService:
    SPREADSHEET_SOURCE = "planilha"

    def __init__(
        self,
        repo: Repository,
        reader: ExcelReader,
        diff: DiffService,
        events: EventLogService,
        key_column_for_carteira: Callable[[str | None], str | None],
        bundle_factory: Callable[[int], dict[str, Any]],
    ) -> None:
        self.repo = repo
        self.reader = reader
        self.diff = diff
        self.events = events
        self.key_column_for_carteira = key_column_for_carteira
        self.bundle_factory = bundle_factory

    def create(self, payload: dict[str, Any]) -> dict[str, Any]:
        self.validate(payload)
        table = self.reader.read_table(payload["arquivo_path"], payload["sheet"], payload.get("senha"))
        payload["last_mtime"] = self.mtime(payload["arquivo_path"])
        payload["source_type"] = self.SPREADSHEET_SOURCE
        negociador_id = self.repo.create_negociador(payload)
        snapshot_id = self.repo.create_snapshot(negociador_id, payload["sheet"], table)
        delta = self.diff.compare(None, table, self.key_column_for_carteira(payload.get("carteira")))
        self.events.create_once(self.events.payload(negociador_id, None, snapshot_id, "initial_snapshot", payload, table, delta))
        return self.bundle_factory(negociador_id)

    def update(self, negociador_id: int, current: dict[str, Any], payload: dict[str, Any]) -> dict[str, Any]:
        merged = {**current, **payload}
        self.validate(merged)
        table = self.reader.read_table(merged["arquivo_path"], merged["sheet"], merged.get("senha"))
        merged["last_mtime"] = self.mtime(merged["arquivo_path"])
        merged["source_type"] = self.SPREADSHEET_SOURCE
        merged["negocial_user_id"] = None
        merged["negocial_username"] = None
        sheet_changed = current["sheet"] != merged["sheet"]
        before_snapshot = self.repo.latest_snapshot(negociador_id, current["sheet"] if sheet_changed else merged["sheet"])
        self.repo.update_negociador(negociador_id, merged)
        if sheet_changed:
            after_snapshot_id = self.repo.create_snapshot(negociador_id, merged["sheet"], table)
            delta = self.new_month_delta(current["sheet"], merged["sheet"], table)
            self.events.create_once(self.events.payload(negociador_id, before_snapshot["id"] if before_snapshot else None, after_snapshot_id, "new_month", merged, table, delta))
            return self.bundle_factory(negociador_id)
        delta = self.diff.compare(before_snapshot["content"] if before_snapshot else None, table, self.key_column_for_carteira(merged.get("carteira")))
        if delta["changes"]:
            after_snapshot_id = self.repo.create_snapshot(negociador_id, merged["sheet"], table)
            self.events.create_once(self.events.payload(negociador_id, before_snapshot["id"] if before_snapshot else None, after_snapshot_id, "manual_update", merged, table, delta))
        return self.bundle_factory(negociador_id)

    def refresh(self, negociador: dict[str, Any], force: bool = False) -> dict[str, Any]:
        negociador_id = int(negociador["id"])
        mtime = self.mtime(negociador["arquivo_path"])
        if not force and negociador.get("last_mtime") == mtime:
            return {"ok": True, "changed": False}
        table = self.reader.read_table(negociador["arquivo_path"], negociador["sheet"], negociador.get("senha"))
        before_snapshot = self.repo.latest_snapshot(negociador_id, negociador["sheet"])
        delta = self.diff.compare(before_snapshot["content"] if before_snapshot else None, table, self.key_column_for_carteira(negociador.get("carteira")))
        self.repo.update_negociador(negociador_id, {"last_mtime": mtime})
        if delta["changes"]:
            snapshot_id = self.repo.create_snapshot(negociador_id, negociador["sheet"], table)
            self.events.create_once(self.events.payload(negociador_id, before_snapshot["id"] if before_snapshot else None, snapshot_id, "file_changed", negociador, table, delta))
            return {"ok": True, "changed": True, "delta": delta}
        return {"ok": True, "changed": False}

    def validate(self, payload: dict[str, Any]) -> None:
        for field in ("nome", "arquivo_path", "sheet"):
            if not str(payload.get(field, "")).strip():
                raise ValueError(f"Campo obrigatorio ausente: {field}")

    def mtime(self, file_path: str) -> float:
        return os.path.getmtime(file_path)

    def new_month_delta(self, before_sheet: str, after_sheet: str, table: dict[str, Any]) -> dict[str, Any]:
        return {
            "summary": {
                "cells_changed": 0,
                "rows_added": 0,
                "rows_removed": 0,
                "columns_added": 0,
                "columns_removed": 0,
                "columns_changed": 0,
                "structure_changed": False,
                "key_column": None,
            },
            "changes": [
                {
                    "type": "new_month",
                    "column": "Novo M\u00eas",
                    "before": before_sheet,
                    "after": after_sheet,
                    "before_sheet": before_sheet,
                    "after_sheet": after_sheet,
                    "message": f"Novo m\u00eas iniciado: {after_sheet}",
                    "row_count": table.get("row_count", 0),
                    "columns": table.get("headers", []),
                }
            ],
        }
