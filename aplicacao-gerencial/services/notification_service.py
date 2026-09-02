from __future__ import annotations

import hashlib
import json
import unicodedata
from datetime import datetime
import threading
import time
from typing import Any

from database.repository import Repository
from services.negociador_service import NegotiadorService
from services.overview_service import OverviewService
from services.parecer_service import ParecerService
from services.protocolo_service import ProtocoloService


class NotificationService:
    def __init__(
        self,
        repo: Repository,
        negociadores: NegotiadorService,
        parecer: ParecerService,
        protocolo: ProtocoloService,
        overview: OverviewService,
        dynamic_tools: Any | None = None,
    ) -> None:
        self.repo = repo
        self.negociadores = negociadores
        self.overview = overview
        self.parecer = parecer
        self.protocolo = protocolo
        self.dynamic_tools = dynamic_tools
        self._cache_lock = threading.Lock()
        self._cache: dict[str, tuple[float, dict[str, Any]]] = {}
        self._refreshing: set[str] = set()
        self._ttl_seconds = 8

    def list_notifications(self, usuario: str) -> dict[str, Any]:
        usuario = self._usuario(usuario)
        now = time.monotonic()
        with self._cache_lock:
            cached = self._cache.get(usuario)
            if cached and now - cached[0] < self._ttl_seconds:
                return cached[1]
            if cached:
                self._schedule_refresh(usuario)
                return cached[1]
        return self._refresh(usuario)

    def _refresh(self, usuario: str) -> dict[str, Any]:
        dismissed = self.repo.list_notification_reads(usuario)
        items = (
            self._overview_notifications(usuario)
            + self._parecer_notifications(usuario, dismissed)
            + self._protocolo_notifications(usuario, dismissed)
            + self._dynamic_tool_notifications(dismissed)
        )
        items.sort(key=lambda item: (item.get("sort_key") or "", item["id"]), reverse=True)
        payload = {
            "count": len(items),
            "overview": len([item for item in items if item["source"] == "overview"]),
            "pareceres": len([item for item in items if item["source"] == "parecer"]),
            "protocolos": len([item for item in items if item["source"] == "protocolo"]),
            "ferramentas": len([item for item in items if item["source"] == "ferramenta"]),
            "items": items[:80],
        }
        payload["version"] = self._version(payload["items"])
        with self._cache_lock:
            self._cache[usuario] = (time.monotonic(), payload)
            self._refreshing.discard(usuario)
        return payload

    def _schedule_refresh(self, usuario: str) -> None:
        if usuario in self._refreshing:
            return
        self._refreshing.add(usuario)
        threading.Thread(target=self._refresh_safely, args=(usuario,), daemon=True, name=f"notifications-{usuario}").start()

    def _refresh_safely(self, usuario: str) -> None:
        try:
            self._refresh(usuario)
        except Exception:
            with self._cache_lock:
                self._refreshing.discard(usuario)

    def clear_cache(self, usuario: str | None = None) -> None:
        with self._cache_lock:
            if usuario:
                self._cache.pop(self._usuario(usuario), None)
            else:
                self._cache.clear()

    def dismiss(self, notification_id: str, usuario: str) -> dict[str, Any]:
        usuario = self._usuario(usuario)
        notification_id = str(notification_id or "").strip()
        if not notification_id:
            raise ValueError("Notificacao invalida")
        if notification_id.startswith(("ALT_", "OVR_")):
            self.overview.mark_read(notification_id, usuario)
        else:
            self.repo.mark_notification_read(notification_id, usuario)
        self.clear_cache(usuario)
        return {"ok": True}

    def dismiss_parecer(self, pk: str, usuario: str) -> None:
        pk = str(pk or "").strip()
        if pk:
            self.repo.mark_notification_read(self._parecer_id(pk), self._usuario(usuario))
            self.clear_cache(usuario)

    def dismiss_pareceres(self, pks: list[str], usuario: str) -> None:
        for pk in pks:
            self.dismiss_parecer(pk, usuario)

    def _overview_notifications(self, usuario: str) -> list[dict[str, Any]]:
        result = []
        for item in self.overview.list_items(usuario, status="unread")[:40]:
            date = str(item.get("dataHora") or "")
            client = item.get("cliente") or item.get("depois") or item.get("antes") or "Cliente nao identificado"
            result.append({
                "id": item["id"],
                "source": "overview",
                "title": "Nova alteracao",
                "message": f"{item.get('campo') or 'Campo alterado'} - {client}",
                "meta": f"{item.get('responsavel') or item.get('usuario') or 'Responsavel'} - {item.get('sheet') or 'Sheet'}",
                "priority": item.get("prioridade") or "normal",
                "dataHora": date,
                "sort_key": date,
                "ref": item["id"],
            })
        return result

    def _parecer_notifications(self, usuario: str, dismissed: set[str]) -> list[dict[str, Any]]:
        config = self.parecer.get_config()
        result = []
        for row in self.parecer.read_pendentes()[:80]:
            pk = str(self._row_value(row, [config.get("pk_column", "PK"), "PK"]) or "").strip()
            if not pk:
                continue
            notification_id = self._parecer_id(pk)
            if notification_id in dismissed:
                continue
            cliente = self._row_value(row, ["CLIENTE", "NOME CLIENTE", "NOME DO CLIENTE", "NOME"]) or "Cliente nao identificado"
            negociador = self._row_value(row, ["OPERADOR", "NEGOCIADOR", "RESPONSAVEL", "RESPONSÁVEL"]) or "Negociador nao informado"
            motivo = self._row_value(row, ["MOTIVO", "MOTIVO PARECER"]) or "Parecer pendente"
            date = str(self._row_value(row, ["DATA", "Data", "data"]) or "")
            sort_key = self._sort_key(date)
            result.append({
                "id": notification_id,
                "source": "parecer",
                "title": "Novo parecer pendente",
                "message": str(cliente),
                "meta": f"{negociador} - {motivo}",
                "priority": "alta",
                "dataHora": date,
                "sort_key": sort_key,
                "pk": pk,
                "ref": pk,
            })
        return result

    def _protocolo_notifications(self, usuario: str, dismissed: set[str]) -> list[dict[str, Any]]:
        result = []
        try:
            records = self.protocolo.pending_records(120)
        except Exception:
            return result
        for row in records:
            row_number = str(row.get("__row_number") or "").strip()
            if not row_number:
                continue
            notification_id = self._protocolo_id(row_number)
            if notification_id in dismissed:
                continue
            cliente = self._row_value(row, ["NOME", "CLIENTE", "NOME CLIENTE"]) or "Cliente nao identificado"
            carteira = self._row_value(row, ["CARTEIRA"]) or "Carteira nao informada"
            processo = self._row_value(row, ["PROCESSO"]) or "Processo nao informado"
            date = str(self._row_value(row, ["DATA DE SOLICITACAO", "DATA DE SOLICITAÇÃO"]) or "")
            result.append({
                "id": notification_id,
                "source": "protocolo",
                "title": "Protocolo pendente",
                "message": str(cliente),
                "meta": f"{carteira} - {processo}",
                "priority": "alta",
                "dataHora": date,
                "sort_key": self._sort_key(date),
                "row": row_number,
                "ref": row_number,
            })
        return result

    def _dynamic_tool_notifications(self, dismissed: set[str]) -> list[dict[str, Any]]:
        if not self.dynamic_tools:
            return []
        try:
            records = self.dynamic_tools.list_open_notifications(80)
        except Exception:
            return []
        result = []
        for row in records:
            notification_id = f"FERRAMENTA_{row['tool_id']}_{row['id']}"
            if notification_id in dismissed:
                continue
            result.append({
                "id": notification_id,
                "source": "ferramenta",
                "title": row["ferramenta"],
                "message": row["titulo"],
                "meta": f"{row['status']} - {row['negociador']} - {row['carteira']}",
                "priority": "alta",
                "dataHora": row["updated_at"],
                "sort_key": row["updated_at"],
                "tool_id": row["tool_id"],
                "record_id": row["id"],
                "ref": f"{row['tool_id']}:{row['id']}",
            })
        return result

    def _row_value(self, row: dict[str, Any], candidates: list[str]) -> Any:
        for candidate in candidates:
            found = self._find_header(row, candidate)
            if found and row.get(found) not in (None, ""):
                return row[found]
        for candidate in candidates:
            normalized = self._normalize(candidate)
            found = next((key for key in row if normalized and normalized in self._normalize(key)), "")
            if found and row.get(found) not in (None, ""):
                return row[found]
        return ""

    def _find_header(self, row: dict[str, Any], name: str) -> str:
        normalized = self._normalize(name)
        return next((key for key in row if self._normalize(key) == normalized), "")

    def _normalize(self, value: Any) -> str:
        text = str(value or "").strip().upper()
        without_accents = "".join(char for char in unicodedata.normalize("NFD", text) if unicodedata.category(char) != "Mn")
        return "".join(char for char in without_accents if char.isalnum())

    def _sort_key(self, value: str) -> str:
        text = str(value or "").strip()
        if not text:
            return datetime.now().isoformat(timespec="seconds")
        try:
            return datetime.fromisoformat(text.split(" ", 1)[0]).isoformat(timespec="seconds")
        except ValueError:
            return text

    def _parecer_id(self, pk: str) -> str:
        return f"PARECER_{pk}"

    def _protocolo_id(self, row_number: str) -> str:
        return f"PROTOCOLO_{row_number}"

    def _usuario(self, usuario: str) -> str:
        return (usuario or "Usuario Local").strip() or "Usuario Local"

    def _version(self, items: list[dict[str, Any]]) -> str:
        raw = json.dumps(
            [
                {
                    "id": item.get("id"),
                    "source": item.get("source"),
                    "sort_key": item.get("sort_key"),
                    "priority": item.get("priority"),
                }
                for item in items
            ],
            ensure_ascii=False,
            sort_keys=True,
            default=str,
        )
        return hashlib.sha1(raw.encode("utf-8")).hexdigest()
