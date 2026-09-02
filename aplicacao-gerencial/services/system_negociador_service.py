from __future__ import annotations

from collections.abc import Callable
import threading
from typing import Any

from database.repository import Repository
from services.diff_service import DiffService
from services.event_log_service import EventLogService
from services.negocial_service import NegocialService


class SystemNegotiadorService:
    SYSTEM_SOURCE = "sistema"

    def __init__(
        self,
        repo: Repository,
        negocial: NegocialService | None,
        diff: DiffService,
        events: EventLogService,
        key_column_for_carteira: Callable[[str | None], str | None],
        bundle_factory: Callable[[int], dict[str, Any]],
    ) -> None:
        self.repo = repo
        self.negocial = negocial
        self.diff = diff
        self.events = events
        self.key_column_for_carteira = key_column_for_carteira
        self.bundle_factory = bundle_factory
        self._refresh_lock = threading.RLock()

    def is_payload(self, payload: dict[str, Any]) -> bool:
        return str(payload.get("source_type") or "").strip().lower() == self.SYSTEM_SOURCE

    def is_negociador(self, negociador: dict[str, Any]) -> bool:
        return str(negociador.get("source_type") or "").strip().lower() == self.SYSTEM_SOURCE

    def create(self, payload: dict[str, Any]) -> dict[str, Any]:
        prepared = self.prepare_payload(payload)
        existing = self.repo.find_system_negociador(str(prepared.get("negocial_username") or ""))
        if existing:
            return self.update(int(existing["id"]), existing, prepared)
        table = self.read_table(prepared)
        prepared["last_mtime"] = self.marker(prepared)
        negociador_id = self.repo.create_negociador(prepared)
        snapshot_id = self.repo.create_snapshot(negociador_id, prepared["sheet"], table)
        delta = self.diff.compare(None, table, self.key_column_for_carteira(prepared.get("carteira")))
        self.events.create_once(self.events.payload(negociador_id, None, snapshot_id, "initial_snapshot", prepared, table, delta))
        return self.bundle_factory(negociador_id)

    def update(self, negociador_id: int, current: dict[str, Any], payload: dict[str, Any]) -> dict[str, Any]:
        prepared = self.prepare_payload(payload, current)
        table = self.read_table(prepared)
        prepared["last_mtime"] = self.marker(prepared)
        before_snapshot = self.repo.latest_snapshot(negociador_id, current.get("sheet") or prepared["sheet"])
        delta = self.diff.compare(before_snapshot["content"] if before_snapshot else None, table, self.key_column_for_carteira(prepared.get("carteira")))
        self.repo.update_negociador(negociador_id, prepared)
        if delta["changes"]:
            snapshot_id = self.repo.create_snapshot(negociador_id, prepared["sheet"], table)
            self.events.create_once(self.events.payload(negociador_id, before_snapshot["id"] if before_snapshot else None, snapshot_id, "manual_update", prepared, table, delta))
        return self.bundle_factory(negociador_id)

    def refresh(self, negociador: dict[str, Any], force: bool = False) -> dict[str, Any]:
        with self._refresh_lock:
            return self._refresh_locked(negociador, force)

    def _refresh_locked(self, negociador: dict[str, Any], force: bool = False) -> dict[str, Any]:
        marker = self.marker(negociador)
        if not force and str(negociador.get("last_mtime") or "") == str(marker):
            return {"ok": True, "changed": False}
        table = self.read_table(negociador)
        negociador_id = int(negociador["id"])
        before_snapshot = self.repo.latest_snapshot(negociador_id, negociador["sheet"])
        delta = self.diff.compare(before_snapshot["content"] if before_snapshot else None, table, self.key_column_for_carteira(negociador.get("carteira")))
        self.repo.update_negociador(negociador_id, {"last_mtime": marker})
        if delta["changes"]:
            snapshot_id = self.repo.create_snapshot(negociador_id, negociador["sheet"], table)
            self.events.create_once(self.events.payload(negociador_id, before_snapshot["id"] if before_snapshot else None, snapshot_id, "file_changed", negociador, table, delta))
            return {"ok": True, "changed": True, "delta": delta}
        return {"ok": True, "changed": False}

    def accept_current_as_baseline(self, username: str) -> dict[str, Any]:
        """Atualiza o snapshot sem gerar timeline para uma edicao originada no Gerencial."""
        with self._refresh_lock:
            return self._accept_current_as_baseline_locked(username)

    def execute_gerencial_change(self, operation: Callable[[], dict[str, Any]]) -> tuple[dict[str, Any], dict[str, Any]]:
        """Serializa a gravacao gerencial com o monitor para que ela nunca vire evento."""
        with self._refresh_lock:
            result = operation()
            baseline_results = []
            usernames = result.get("affected_usernames") or []
            for username in dict.fromkeys(str(item or "").strip() for item in usernames):
                if not username:
                    continue
                try:
                    baseline = self._accept_current_as_baseline_locked(username)
                except Exception as exc:
                    baseline = {"ok": False, "updated": False, "error": str(exc)}
                baseline_results.append({"username": username, **baseline})
            summary = {
                "ok": all(item.get("ok") for item in baseline_results),
                "results": baseline_results,
                "updated": sum(1 for item in baseline_results if item.get("updated")),
            }
            return result, summary

    def _accept_current_as_baseline_locked(self, username: str) -> dict[str, Any]:
        username = str(username or "").strip()
        if not username:
            return {"ok": True, "updated": False, "reason": "empty_username"}
        negociador = self.repo.find_system_negociador(username)
        if not negociador or not negociador.get("active"):
            return {"ok": True, "updated": False, "reason": "negociador_not_monitored"}

        table = self.read_table(negociador)
        negociador_id = int(negociador["id"])
        before_snapshot = self.repo.latest_snapshot(negociador_id, negociador["sheet"])
        delta = self.diff.compare(
            before_snapshot["content"] if before_snapshot else None,
            table,
            self.key_column_for_carteira(negociador.get("carteira")),
        )
        marker = self.marker(negociador)
        if not delta["changes"]:
            self.repo.update_negociador(negociador_id, {"last_mtime": marker})
            return {"ok": True, "updated": False, "reason": "already_current"}

        snapshot_id = self.repo.create_snapshot(negociador_id, negociador["sheet"], table)
        self.repo.update_negociador(negociador_id, {"last_mtime": marker})
        return {
            "ok": True,
            "updated": True,
            "negociador_id": negociador_id,
            "snapshot_id": snapshot_id,
            "changes_suppressed": len(delta["changes"]),
        }

    def prepare_payload(self, payload: dict[str, Any], current: dict[str, Any] | None = None) -> dict[str, Any]:
        if not self.negocial:
            raise ValueError("Integracao com sistema negocial nao configurada.")
        username = str(
            payload.get("negocial_username")
            or payload.get("usuario")
            or payload.get("username")
            or (current or {}).get("negocial_username")
            or ""
        ).strip()
        password = str(payload.get("negocial_password") or payload.get("senha") or "").strip()
        carteira = str(payload.get("carteira") or (current or {}).get("carteira") or "").strip()
        if not username:
            raise ValueError("Usuario do sistema negocial obrigatorio.")
        if not carteira:
            raise ValueError("Carteira obrigatoria para negociador via sistema.")
        meta_pagamento = payload.get("meta_pagamento")
        if meta_pagamento in (None, ""):
            meta_pagamento = (current or {}).get("meta_pagamento") or 70000
        user = self.negocial.upsert_user(username, password or None, carteira, meta_pagamento)
        return {
            **(current or {}),
            **payload,
            "nome": str(payload.get("nome") or username).strip() or username,
            "carteira": carteira,
            "arquivo_path": f"negocial://{username}",
            "sheet": NegocialService.PRODUCAO_SHEET,
            "senha": None,
            "source_type": self.SYSTEM_SOURCE,
            "negocial_user_id": user["id"],
            "negocial_username": username,
            "meta_pagamento": user.get("meta_pagamento") or meta_pagamento,
        }

    def read_table(self, negociador: dict[str, Any]) -> dict[str, Any]:
        if not self.negocial:
            raise ValueError("Integracao com sistema negocial nao configurada.")
        return self.negocial.read_producao_table(str(negociador.get("negocial_username") or ""))

    def marker(self, negociador: dict[str, Any]) -> str:
        if not self.negocial:
            raise ValueError("Integracao com sistema negocial nao configurada.")
        return self.negocial.producao_marker(str(negociador.get("negocial_username") or ""))
