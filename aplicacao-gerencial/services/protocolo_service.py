from __future__ import annotations

import copy
import json
import threading
import unicodedata
from datetime import datetime
from pathlib import Path
from typing import Any

from database.repository import Repository


class ProtocoloError(RuntimeError):
    pass


DEFAULT_CONFIG = {
    "storage": "database",
    "clear_completion_when_reopened": True,
}

STATUSES = {"PENDENTE", "CONCLUIDO"}

DB_HEADERS = {
    "DATA": "data_mes",
    "CARTEIRA": "carteira",
    "NOME": "nome",
    "PJ": "pj",
    "PROCESSO": "processo",
    "DATA DE SOLICITACAO": "data_solicitacao",
    "STATUS": "status",
    "DATA DE CONCLUSAO": "data_conclusao",
    "OBSERVACAO": "observacao",
}


class ProtocoloService:
    def __init__(self, repo: Repository, data_dir: Path) -> None:
        self.repo = repo
        self.data_dir = data_dir
        self.config_path = data_dir / "protocolo_config.json"
        self._lock = threading.Lock()
        self._cache_lock = threading.Lock()
        self._records_cache: dict[str, Any] | None = None
        if not self.config_path.exists():
            self.save_config(DEFAULT_CONFIG)

    def get_config(self) -> dict[str, Any]:
        stored = self._read_json(self.config_path, {})
        return DEFAULT_CONFIG | {
            "clear_completion_when_reopened": bool(stored.get("clear_completion_when_reopened", DEFAULT_CONFIG["clear_completion_when_reopened"])),
        }

    def save_config(self, payload: dict[str, Any]) -> dict[str, Any]:
        config = self.get_config()
        if "clear_completion_when_reopened" in payload:
            config["clear_completion_when_reopened"] = bool(payload.get("clear_completion_when_reopened"))
        config["storage"] = "database"
        self.config_path.write_text(json.dumps(config, ensure_ascii=False, indent=2), encoding="utf-8")
        return config

    def records(self) -> list[dict[str, Any]]:
        with self._cache_lock:
            if self._records_cache:
                return copy.deepcopy(self._records_cache["records"])
        result = [self._record_from_db(row) for row in self.repo.list_protocolos()]
        with self._cache_lock:
            self._records_cache = {
                "records": copy.deepcopy(result),
                "updated_at": datetime.now().isoformat(timespec="seconds"),
            }
        return result

    def pending_records(self, limit: int | None = None) -> list[dict[str, Any]]:
        result = [self._record_from_db(row) for row in self.repo.list_protocolos(pending_only=True, limit=limit)]
        return result[: max(0, int(limit))] if limit else result

    def clear_cache(self) -> None:
        with self._cache_lock:
            self._records_cache = None

    def dashboard(self) -> dict[str, Any]:
        records = self.records()
        current_month = self._month_label(datetime.now())
        return {
            "total": len(records),
            "solicitados": len([record for record in records if self._status(record) == "PENDENTE"]),
            "pendentes": len([record for record in records if self._status(record) == "PENDENTE"]),
            "concluidos": len([record for record in records if self._status(record) == "CONCLUIDO"]),
            "mes_atual": len([record for record in records if self._normalize(record.get("DATA")) == self._normalize(current_month)]),
            "updated_at": datetime.now().isoformat(timespec="seconds"),
        }

    def create(self, payload: dict[str, Any], user: str) -> dict[str, Any]:
        self._validate_create(payload)
        record = {
            "data_mes": self._month_label(datetime.now()),
            "carteira": str(payload.get("carteira", "")).strip(),
            "nome": str(payload.get("nome", "")).strip(),
            "pj": str(payload.get("pj", "")).strip(),
            "processo": str(payload.get("processo", "")).strip(),
            "data_solicitacao": datetime.now().strftime("%d/%m/%Y"),
            "status": "PENDENTE",
            "data_conclusao": "",
            "observacao": str(payload.get("observacao", "")).strip(),
            "extra": {},
        }
        with self._lock:
            created = self.repo.create_protocolo(record, user)
            self.clear_cache()
        return {"ok": True, "row": created["row_key"], "record": self._record_from_db(created)}

    def update_status(self, row_number: int, status: str, user: str) -> dict[str, Any]:
        row_number = int(row_number or 0)
        status = self._normalize_status(status)
        if row_number <= 0:
            raise ProtocoloError("Linha do protocolo invalida.")
        current = self._find_db_record(row_number)
        if not current:
            raise ProtocoloError("Protocolo nao encontrado.")
        completion = str(current.get("data_conclusao") or "")
        if status == "CONCLUIDO":
            completion = datetime.now().strftime("%d/%m/%Y")
        elif self.get_config().get("clear_completion_when_reopened"):
            completion = ""
        with self._lock:
            updated = self.repo.update_protocolo_status(row_number, status, completion, user)
            self.clear_cache()
        return {"ok": True, "row": row_number, "status": status, "record": self._record_from_db(updated)}

    def update_cell(self, row_number: int, header: str, value: Any, user: str) -> dict[str, Any]:
        row_number = int(row_number or 0)
        header = str(header or "").strip()
        if row_number <= 0:
            raise ProtocoloError("Linha do protocolo invalida.")
        if not header:
            raise ProtocoloError("Coluna do protocolo invalida.")
        if self._normalize(header) == "STATUS":
            raise ProtocoloError("Use o controle de status para alterar esta coluna.")
        field = self._field_for_header(header)
        if not field:
            raise ProtocoloError(f"Coluna '{header}' nao encontrada.")
        with self._lock:
            updated = self.repo.update_protocolo_field(row_number, field, value, user)
            self.clear_cache()
        return {"ok": True, "row": row_number, "header": header, "value": value, "record": self._record_from_db(updated)}

    def _find_db_record(self, row_key: int) -> dict[str, Any] | None:
        return next((row for row in self.repo.list_protocolos() if int(row.get("row_key") or 0) == int(row_key)), None)

    def _record_from_db(self, row: dict[str, Any]) -> dict[str, Any]:
        extra = row.get("extra") or {}
        record = {
            "DATA": row.get("data_mes") or "",
            "CARTEIRA": row.get("carteira") or "",
            "NOME": row.get("nome") or "",
            "PJ": row.get("pj") or "",
            "PROCESSO": row.get("processo") or "",
            "DATA DE SOLICITACAO": row.get("data_solicitacao") or "",
            "STATUS": self._normalize_status(row.get("status") or "PENDENTE"),
            "DATA DE CONCLUSAO": row.get("data_conclusao") or "",
            "OBSERVACAO": row.get("observacao") or "",
            "__row_number": row.get("row_key"),
            "__id": row.get("id"),
            "__source": row.get("source") or "database",
            "__updated_at": row.get("updated_at"),
        }
        for key, value in extra.items():
            if key not in record and not str(key).startswith("__"):
                record[key] = value
        return record

    def _field_for_header(self, header: str) -> str:
        normalized = self._normalize(header)
        return next((field for label, field in DB_HEADERS.items() if self._normalize(label) == normalized), "")

    def _validate_create(self, payload: dict[str, Any]) -> None:
        labels = {"carteira": "Carteira", "nome": "Nome", "pj": "PJ", "processo": "Processo"}
        for key, label in labels.items():
            if not str(payload.get(key, "")).strip():
                raise ProtocoloError(f"Campo obrigatorio ausente: {label}.")

    def _normalize_status(self, status: Any) -> str:
        value = self._normalize(status)
        if value not in STATUSES:
            raise ProtocoloError("Status invalido.")
        return value

    def _status(self, record: dict[str, Any]) -> str:
        return self._normalize_status(record.get("STATUS") or "PENDENTE")

    def _month_label(self, value: datetime) -> str:
        months = ["jan", "fev", "mar", "abr", "mai", "jun", "jul", "ago", "set", "out", "nov", "dez"]
        return f"{months[value.month - 1]}/{str(value.year)[-2:]}"

    def _normalize(self, value: Any) -> str:
        text = str(value or "").strip().upper()
        without_accents = "".join(char for char in unicodedata.normalize("NFD", text) if unicodedata.category(char) != "Mn")
        return "".join(char for char in without_accents if char.isalnum())

    def _read_json(self, path: Path, fallback):
        if not path.exists():
            return fallback
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return fallback
