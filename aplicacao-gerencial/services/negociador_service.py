from __future__ import annotations

from collections.abc import Callable
from typing import Any

from database.repository import Repository
from services.diff_service import DiffService
from services.event_log_service import EventLogService
from services.excel_reader import ExcelReader
from services.negocial_service import NegocialService
from services.overview_builder import OverviewBuilder
from services.snapshot_service import SnapshotService
from services.spreadsheet_negociador_service import SpreadsheetNegotiadorService
from services.system_negociador_service import SystemNegotiadorService


class NegotiadorService:
    def __init__(self, repo: Repository, reader: ExcelReader, negocial: NegocialService | None = None) -> None:
        self.repo = repo
        self.reader = reader
        self.negocial = negocial
        self.diff = DiffService()
        self.snapshots = SnapshotService(self.repo)
        self.overview_builder = OverviewBuilder()
        self.events = EventLogService(
            self.repo,
            row_values=self.overview_builder.row_values,
            normalized_value=self.overview_builder.normalized_value,
            is_noop_change=self.overview_builder.is_noop_change,
        )
        self.system = SystemNegotiadorService(
            self.repo,
            self.negocial,
            self.diff,
            self.events,
            key_column_for_carteira=self._key_column_for_carteira,
            bundle_factory=self.get_negociador_bundle,
        )
        self.spreadsheets = SpreadsheetNegotiadorService(
            self.repo,
            self.reader,
            self.diff,
            self.events,
            key_column_for_carteira=self._key_column_for_carteira,
            bundle_factory=self.get_negociador_bundle,
        )

    def list_negociadores(self) -> list[dict[str, Any]]:
        negociadores = [self._public_negociador(item) for item in self.repo.list_negociadores()]
        if not self.negocial:
            return [{**item, "online": False} for item in negociadores]
        try:
            users = {
                str(user.get("username") or "").strip().lower(): user
                for user in self.negocial.list_users()
            }
        except Exception:
            # Presenca e informativa; uma indisponibilidade do Negocial nao pode bloquear a listagem.
            users = {}
        return [
            {
                **item,
                "online": bool(users.get(str(item.get("negocial_username") or "").strip().lower(), {}).get("online")),
            }
            for item in negociadores
        ]

    def create_negociador(self, payload: dict[str, Any]) -> dict[str, Any]:
        if self.system.is_payload(payload):
            return self.system.create(payload)
        return self.spreadsheets.create(payload)

    def update_negociador(self, negociador_id: int, payload: dict[str, Any]) -> dict[str, Any]:
        current = self.repo.get_negociador(negociador_id)
        if not current:
            raise ValueError("Negociador nao encontrado")
        merged = {**current, **payload}
        if self.system.is_payload(merged):
            return self.system.update(negociador_id, current, merged)
        return self.spreadsheets.update(negociador_id, current, payload)

    def delete_negociador(self, negociador_id: int) -> None:
        self.repo.soft_delete_negociador(negociador_id)

    def refresh_negociador(self, negociador_id: int, force: bool = False) -> dict[str, Any]:
        negociador = self.repo.get_negociador(negociador_id)
        if not negociador or not negociador["active"]:
            return {"ok": False, "message": "Negociador inativo ou nao encontrado"}
        if self.system.is_negociador(negociador):
            return self.system.refresh(negociador, force)
        return self.spreadsheets.refresh(negociador, force)

    def accept_gerencial_baselines(self, usernames: list[str] | tuple[str, ...] | set[str]) -> dict[str, Any]:
        results = []
        for username in dict.fromkeys(str(item or "").strip() for item in usernames):
            if username:
                try:
                    result = self.system.accept_current_as_baseline(username)
                except Exception as exc:
                    result = {"ok": False, "updated": False, "error": str(exc)}
                results.append({"username": username, **result})
        return {
            "ok": all(item.get("ok") for item in results),
            "results": results,
            "updated": sum(1 for item in results if item.get("updated")),
        }

    def execute_gerencial_change(self, operation: Callable[[], dict[str, Any]]) -> tuple[dict[str, Any], dict[str, Any]]:
        return self.system.execute_gerencial_change(operation)

    def get_negociador_bundle(self, negociador_id: int) -> dict[str, Any]:
        negociador = self.repo.get_negociador(negociador_id)
        return {"negociador": self._public_negociador(negociador), "data": self.get_table_data(negociador_id), "events": self.get_events(negociador_id)}

    @staticmethod
    def _public_negociador(negociador: dict[str, Any] | None) -> dict[str, Any] | None:
        if negociador is None:
            return None
        return {key: value for key, value in negociador.items() if key != "senha"}

    def get_table_data(self, negociador_id: int) -> dict[str, Any]:
        negociador = self.repo.get_negociador(negociador_id)
        if not negociador:
            raise ValueError("Negociador nao encontrado")
        return self.snapshots.latest_table_data(negociador)

    def get_month_snapshot(self, negociador_id: int, month_key: str) -> dict[str, Any]:
        negociador = self.repo.get_negociador(negociador_id)
        if not negociador:
            raise ValueError("Negociador nao encontrado")
        return self.snapshots.month_snapshot(negociador, month_key)

    def get_events(self, negociador_id: int) -> list[dict[str, Any]]:
        return self.events.list_events(negociador_id)

    def get_timeline(self, negociador_id: int) -> dict[str, Any]:
        return self.events.build_timeline(negociador_id)

    def get_corrections(self, negociador_id: int, limit: int = 200) -> list[dict[str, Any]]:
        negociador = self.repo.get_negociador(negociador_id)
        if not negociador:
            raise ValueError("Negociador nao encontrado")
        if not self.system.is_negociador(negociador) or not self.negocial:
            return []
        return self.negocial.list_production_corrections(
            str(negociador.get("negocial_username") or negociador.get("nome") or ""),
            limit,
        )

    def get_all_events(self, limit: int = 1500) -> list[dict[str, Any]]:
        return self.events.list_all_events(limit)

    def get_event(self, event_id: int) -> dict[str, Any]:
        return self.events.get_event(event_id)

    def _key_column_for_carteira(self, carteira: str | None) -> str | None:
        normalized = str(carteira or "").strip().upper()
        if "ALPHA" in normalized:
            return "DEBIT ID"
        if normalized == "GAMMA" or " GAMMA" in normalized or "GAMMA " in normalized:
            return "NPJ"
        if "BETA" in normalized:
            return "SUITID"
        return None
