from __future__ import annotations

import os
import json
import threading
import time
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Any

import pandas as pd

from database.external_crm_repository import ExternalCrmRepository
from services.defasagem_domain import (
    assign_priority_queue,
    attach_category_details,
    build_guarantee_summary,
    build_metrics,
    build_special_defasagem,
    build_trigger_summary,
    enrich_contracts,
    export_columns,
    filter_dataframe,
    normalize_text,
    prepare_contract_keys,
    read_contracts_excel,
    read_guarantees_excel,
    read_triggers_excel,
    to_csv_bytes,
    to_excel_bytes,
)


APPLICATION_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_PROJECT = APPLICATION_ROOT / "data" / "defasagem"


@dataclass(frozen=True)
class DefasagemSettings:
    postgres_host: str
    postgres_port: int
    postgres_db: str
    postgres_user: str
    postgres_password: str
    postgres_schema: str
    postgres_table: str
    default_excel_path: Path
    default_garantias_path: Path
    default_gatilhos_path: Path
    sem_retorno_dias: int
    negociacao_alert_dias: int
    possivel_negocio_alert_dias: int
    desinteresse_alert_dias: int
    critico_dias: int
    cache_ttl_seconds: int
    excluded_operators: tuple[str, ...]


def _env_file(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    if not path.exists():
        return values
    for raw in path.read_text(encoding="utf-8-sig").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip().strip('"').strip("'")
    return values


def load_defasagem_settings() -> DefasagemSettings:
    project = Path(os.environ.get("DEFASAGEM_PROJECT_DIR", str(DEFAULT_PROJECT))).expanduser()
    source = _env_file(Path(os.environ.get("DEFASAGEM_ENV_PATH", str(project / ".env"))))

    def value(name: str, default: str) -> str:
        return os.environ.get(f"DEFASAGEM_{name}") or source.get(name) or default

    def source_path(name: str, default: str) -> Path:
        path = Path(value(name, default)).expanduser()
        return path if path.is_absolute() else project / path

    return DefasagemSettings(
        postgres_host=value("POSTGRES_HOST", "localhost"),
        postgres_port=int(value("POSTGRES_PORT", "5432")),
        postgres_db=value("POSTGRES_DB", "crm"),
        postgres_user=value("POSTGRES_USER", "postgres"),
        postgres_password=value("POSTGRES_PASSWORD", ""),
        postgres_schema=value("POSTGRES_SCHEMA", "public"),
        postgres_table=value("POSTGRES_TABLE", "acionamentos"),
        default_excel_path=source_path("DEFAULT_EXCEL_PATH", "uploads/contratos_ativos.xlsx"),
        default_garantias_path=source_path("DEFAULT_GARANTIAS_PATH", "uploads/garantias.xlsx"),
        default_gatilhos_path=source_path("DEFAULT_GATILHOS_PATH", "uploads/gatilhos.xlsx"),
        sem_retorno_dias=int(value("SEM_RETORNO_DIAS", "30")),
        negociacao_alert_dias=int(value("NEGOCIACAO_ALERT_DIAS", "7")),
        possivel_negocio_alert_dias=int(value("POSSIVEL_NEGOCIO_ALERT_DIAS", "7")),
        desinteresse_alert_dias=int(value("DESINTERESSE_ALERT_DIAS", "90")),
        critico_dias=int(value("CRITICO_DIAS", "180")),
        cache_ttl_seconds=max(30, int(value("CACHE_TTL_SECONDS", "300"))),
        excluded_operators=tuple(item.strip() for item in value("EXCLUDED_OPERATORS", "adrianof").split(",") if item.strip()),
    )


class DefasagemService:
    def __init__(self) -> None:
        self.settings = load_defasagem_settings()
        self.repository = ExternalCrmRepository(self.settings)
        self.source_config_path = DEFAULT_PROJECT / "source_directory.json"
        self._lock = threading.RLock()
        self._snapshot: dict[str, Any] | None = None
        self._snapshot_history: dict[str, dict[str, Any]] = {}
        self._expires_at = 0.0
        self._refreshing = False

    def source_config(self) -> dict[str, Any]:
        directory = self._source_directory()
        paths = self._source_paths(directory)
        available = directory.is_dir()
        readable = available and os.access(directory, os.R_OK)
        return {
            "path": str(directory),
            "default_path": str(self.settings.default_excel_path.parent.resolve()),
            "custom": directory != self.settings.default_excel_path.parent.resolve(),
            "available": available,
            "readable": readable,
            "files": {
                "contracts": self._file_status(paths["contracts"], required=True),
                "guarantees": self._file_status(paths["guarantees"]),
                "triggers": self._file_status(paths["triggers"]),
            },
        }

    def configure_source_directory(self, path: str) -> dict[str, Any]:
        raw = os.path.expandvars(os.path.expanduser(str(path or "").strip().strip('"')))
        target = Path(raw) if raw else self.settings.default_excel_path.parent
        if not target.is_absolute():
            raise RuntimeError("Informe um caminho absoluto para as planilhas da Defasagem.")
        target = target.resolve()
        if not target.is_dir():
            raise RuntimeError(f"O diretorio informado nao existe: {target}")
        if not os.access(target, os.R_OK):
            raise RuntimeError(f"O diretorio informado nao pode ser lido: {target}")
        contracts = self._source_paths(target)["contracts"]
        if not contracts.is_file():
            raise RuntimeError(f"Base de contratos nao encontrada: {contracts}")

        with self._lock:
            self.source_config_path.parent.mkdir(parents=True, exist_ok=True)
            temporary = self.source_config_path.with_suffix(".tmp")
            temporary.write_text(
                json.dumps({
                    "path": str(target),
                    "updated_at": datetime.now().isoformat(timespec="seconds"),
                }, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            temporary.replace(self.source_config_path)
            self._snapshot = None
            self._snapshot_history.clear()
            self._expires_at = 0.0

        return {"ok": True, "source": self.source_config()}

    def _source_directory(self) -> Path:
        try:
            payload = json.loads(self.source_config_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            payload = {}
        configured = str(payload.get("path") or "").strip() if isinstance(payload, dict) else ""
        return (Path(configured).expanduser() if configured else self.settings.default_excel_path.parent).resolve()

    def _source_paths(self, directory: Path | None = None) -> dict[str, Path]:
        root = directory or self._source_directory()
        return {
            "contracts": root / self.settings.default_excel_path.name,
            "guarantees": root / self.settings.default_garantias_path.name,
            "triggers": root / self.settings.default_gatilhos_path.name,
        }

    @staticmethod
    def _file_status(path: Path, required: bool = False) -> dict[str, Any]:
        exists = path.is_file()
        return {
            "name": path.name,
            "path": str(path),
            "required": required,
            "exists": exists,
            "size_bytes": path.stat().st_size if exists else 0,
        }

    def _build_snapshot(self) -> dict[str, Any]:
        settings = self.settings
        paths = self._source_paths()
        if not paths["contracts"].exists():
            raise RuntimeError(f"Base de contratos nao encontrada: {paths['contracts']}")
        contracts = read_contracts_excel(paths["contracts"], settings.excluded_operators)
        keys = prepare_contract_keys(contracts)
        actions, discador = self.repository.latest_actions_bundle(keys)
        guarantees = read_guarantees_excel(paths["guarantees"] if paths["guarantees"].exists() else None)
        triggers = read_triggers_excel(paths["triggers"] if paths["triggers"].exists() else None)
        data = enrich_contracts(contracts, actions, settings, card_actions_df=discador)
        data = attach_category_details(data, guarantees, triggers)
        data = assign_priority_queue(data)
        return {
            "data": data,
            "guarantees": guarantees,
            "triggers": triggers,
            "timeline": self.repository.timeline(),
            "operator_activity": self.repository.operator_activity(),
            "loaded_at": datetime.now().astimezone(),
            "contracts": len(contracts),
            "actions": len(actions),
        }

    def _store_snapshot(self, snapshot: dict[str, Any]) -> dict[str, Any]:
        self._snapshot = snapshot
        history = getattr(self, "_snapshot_history", None)
        if history is None:
            history = {}
            self._snapshot_history = history
        version = snapshot["loaded_at"].isoformat()
        history[version] = snapshot
        while len(history) > 3:
            history.pop(next(iter(history)))
        self._expires_at = time.monotonic() + self.settings.cache_ttl_seconds
        return snapshot

    def _snapshot_by_version(self, version: str) -> dict[str, Any]:
        if not version:
            return self._load_snapshot()
        with self._lock:
            current = self._snapshot
            if current is not None and current["loaded_at"].isoformat() == version:
                return current
            archived = getattr(self, "_snapshot_history", {}).get(version)
            if archived is not None:
                return archived
        return self._load_snapshot()

    def _refresh_in_background(self) -> None:
        try:
            snapshot = self._build_snapshot()
            with self._lock:
                self._store_snapshot(snapshot)
        finally:
            with self._lock:
                self._refreshing = False

    def _load_snapshot(self, force: bool = False) -> dict[str, Any]:
        with self._lock:
            if self._snapshot is not None and not force:
                if time.monotonic() >= self._expires_at and not self._refreshing:
                    self._refreshing = True
                    threading.Thread(
                        target=self._refresh_in_background,
                        name="defasagem-refresh",
                        daemon=True,
                    ).start()
                return self._snapshot

            snapshot = self._build_snapshot()
            return self._store_snapshot(snapshot)

    @staticmethod
    def _filter_values(filters: dict[str, Any]) -> dict[str, Any]:
        prepared: dict[str, Any] = {"busca": str(filters.get("busca") or "")}
        for key in ("carteira", "fase", "nome_op", "uf", "gecor", "operador", "faixa_defasagem", "ultimo_acionamento", "situacao_especial"):
            value = filters.get(key)
            if isinstance(value, str) and value.strip():
                prepared[key] = [value.strip()]
            elif isinstance(value, (list, tuple)) and value:
                prepared[key] = list(value)
        for key in ("filtro_operacional", "operador_sem_retorno", "tipo_defasagem"):
            value = str(filters.get(key) or "").strip()
            if value:
                prepared[key] = value
        return prepared

    def _filtered(self, filters: dict[str, Any], force: bool = False) -> tuple[dict[str, Any], pd.DataFrame]:
        snapshot = self._load_snapshot(force)
        return snapshot, filter_dataframe(snapshot["data"], self._filter_values(filters))

    @staticmethod
    def _counts(
        df: pd.DataFrame,
        column: str,
        limit: int | None = None,
    ) -> list[dict[str, Any]]:
        if df.empty or column not in df:
            return []
        grouped = df.groupby(column, dropna=False)["contrato_key"].nunique().sort_values(ascending=False)
        if limit is not None:
            grouped = grouped.head(limit)
        return [{"label": str(label or "Nao informado"), "value": int(count)} for label, count in grouped.items()]

    @staticmethod
    def _frame_records(df: pd.DataFrame) -> list[dict[str, Any]]:
        clean = df.copy()
        clean = clean.where(pd.notna(clean), None)
        result: list[dict[str, Any]] = []
        for row in clean.to_dict(orient="records"):
            result.append({key: value.isoformat() if isinstance(value, (date, datetime, pd.Timestamp)) else value for key, value in row.items()})
        return result

    @classmethod
    def _records(cls, df: pd.DataFrame) -> list[dict[str, Any]]:
        return cls._frame_records(export_columns(df))

    @staticmethod
    def _options(df: pd.DataFrame) -> dict[str, list[str]]:
        options: dict[str, list[str]] = {}
        for column in ("carteira", "fase", "nome_op", "uf", "gecor", "operador", "faixa_defasagem", "ultimo_acionamento", "situacao_especial"):
            if column in df:
                options[column] = sorted({str(item) for item in df[column].dropna().tolist() if str(item).strip()})
        if "operador" in df and "sem_retorno" in df:
            pending = df[df["sem_retorno"].fillna(False)]
            options["operadores_sem_retorno"] = sorted({
                str(item).strip()
                for item in pending["operador"].dropna().tolist()
                if str(item).strip() and str(item).strip().lower() != "sem operador"
            })
        return options

    def dashboard(self, filters: dict[str, Any], force: bool = False) -> dict[str, Any]:
        snapshot, data = self._filtered(filters, force)
        if "_prioridade_ordem" not in data or "prioridade_fila" not in data:
            data = assign_priority_queue(data)
        special = build_special_defasagem(data)
        guarantees = build_guarantee_summary(snapshot["guarantees"], data)
        triggers = build_trigger_summary(snapshot["triggers"], data)
        metrics = build_metrics(data, use_card_defasagem=True)
        metrics["garantias_total"] = int(guarantees.get("quantidade", pd.Series(dtype="int64")).sum())
        metrics["gatilhos_total"] = int(triggers.get("quantidade", pd.Series(dtype="int64")).sum())
        critical_mask = data.get("is_critico", pd.Series(False, index=data.index)).fillna(False)
        metrics["clientes_criticos"] = int(
            data.loc[critical_mask, "contrato_key"].nunique()
            if "contrato_key" in data
            else critical_mask.sum()
        )
        priority_clients = data.sort_values(
            ["_prioridade_ordem", "dias_sem_acionamento"],
            ascending=[True, False],
            na_position="last",
        ).head(20)
        operator_portfolio_alerts = self._operator_portfolio_alerts(data)
        return {
            "metrics": metrics,
            "options": self._options(snapshot["data"]),
            "counts": {
                "carteiras": self._counts(data, "carteira"),
                "operadores": self._counts(data, "nome_op"),
                "ufs": self._counts(data, "uf"), "gecors": self._counts(data, "gecor"),
                "acionamentos": self._counts(data, "ultimo_acionamento"),
            },
            "special": self._frame_records(special),
            "guarantees": self._frame_records(guarantees),
            "triggers": self._frame_records(triggers),
            "priority_clients": self._records(priority_clients),
            "operator_portfolio_alerts": operator_portfolio_alerts,
            "linked_analysis": self._linked_analysis(data),
            "timeline": self._frame_records(snapshot["timeline"]),
            "ranking": self._frame_records(snapshot["operator_activity"]),
            "meta": {"loaded_at": snapshot["loaded_at"].isoformat(), "snapshot_version": snapshot["loaded_at"].isoformat(), "contracts": snapshot["contracts"], "actions": snapshot["actions"], "filtered": len(data), "cache_ttl": self.settings.cache_ttl_seconds},
        }

    @classmethod
    def _operator_portfolio_alerts(cls, data: pd.DataFrame) -> list[dict[str, Any]]:
        if data.empty:
            return []
        source = data.copy()
        for column in ("nome_op", "carteira"):
            if column not in source:
                source[column] = "Nao informado"
        source["negociacao_sem_retorno"] = source.get(
            "negociacao_sem_retorno",
            pd.Series(False, index=source.index),
        ).fillna(False).astype(int)
        source["possivel_negocio_sem_retorno"] = source.get(
            "possivel_negocio_sem_retorno",
            pd.Series(False, index=source.index),
        ).fillna(False).astype(int)
        grouped = (
            source.groupby(["nome_op", "carteira"], dropna=False)[
                ["negociacao_sem_retorno", "possivel_negocio_sem_retorno"]
            ]
            .sum()
            .reset_index()
        )
        grouped["total"] = grouped["negociacao_sem_retorno"] + grouped["possivel_negocio_sem_retorno"]
        grouped = grouped[grouped["total"].gt(0)].sort_values(
            ["total", "negociacao_sem_retorno", "nome_op"],
            ascending=[False, False, True],
        )
        return cls._frame_records(grouped)

    @classmethod
    def _linked_analysis(cls, data: pd.DataFrame) -> dict[str, Any]:
        if data.empty:
            linked = data.copy()
        else:
            has_trigger = data.get("tem_gatilho", pd.Series(False, index=data.index)).fillna(False)
            has_guarantee = data.get("tem_garantia", pd.Series(False, index=data.index)).fillna(False)
            linked = data[has_trigger | has_guarantee].copy()

        total_base = int(data.get("contrato_key", pd.Series(dtype="string")).nunique())
        linked_total = int(linked.get("contrato_key", pd.Series(dtype="string")).nunique())
        linked_metrics = build_metrics(linked, use_card_defasagem=True)
        linked_metrics.update({
            "total_base": total_base,
            "sem_vinculo": max(0, total_base - linked_total),
            "com_gatilho": cls._unique_linked_count(linked, "tem_gatilho"),
            "com_garantia": cls._unique_linked_count(linked, "tem_garantia"),
            "gatilhos_total": int(pd.to_numeric(linked.get("quantidade_gatilhos", pd.Series(dtype="int64")), errors="coerce").fillna(0).sum()),
            "garantias_total": int(pd.to_numeric(linked.get("quantidade_garantias", pd.Series(dtype="int64")), errors="coerce").fillna(0).sum()),
            "com_ambos": cls._unique_mask_count(linked, (
                linked.get("tem_gatilho", pd.Series(False, index=linked.index)).fillna(False)
                & linked.get("tem_garantia", pd.Series(False, index=linked.index)).fillna(False)
            )),
            "clientes_criticos": cls._unique_mask_count(
                linked,
                linked.get("is_critico", pd.Series(False, index=linked.index)).fillna(False),
            ),
        })
        columns = [
            "contrato", "cliente", "carteira", "nome_op", "gatilhos", "garantias",
            "ultimo_acionamento", "data_ultimo_acionamento", "dias_sem_acionamento",
            "faixa_defasagem", "prioridade_fila",
        ]
        available = [column for column in columns if column in linked]
        items = linked.sort_values(
            ["_prioridade_ordem", "dias_sem_acionamento"],
            ascending=[True, False],
            na_position="last",
        ).head(200)
        return {
            "metrics": linked_metrics,
            "counts": {
                "faixas": cls._counts(linked, "faixa_defasagem_cards"),
                "operadores": cls._counts(linked, "nome_op"),
                "carteiras": cls._counts(linked, "carteira"),
            },
            "items": cls._frame_records(items[available]),
            "total": linked_total,
        }

    @staticmethod
    def _unique_mask_count(data: pd.DataFrame, mask: pd.Series) -> int:
        if data.empty:
            return 0
        if "contrato_key" in data:
            return int(data.loc[mask, "contrato_key"].nunique())
        return int(mask.sum())

    @classmethod
    def _unique_linked_count(cls, data: pd.DataFrame, flag_column: str) -> int:
        mask = data.get(flag_column, pd.Series(False, index=data.index)).fillna(False)
        return cls._unique_mask_count(data, mask)

    def operators(self, filters: dict[str, Any]) -> dict[str, Any]:
        _, data = self._filtered(filters)
        rows = []
        for name, group in data.groupby("nome_op", dropna=False):
            metrics = build_metrics(group, use_card_defasagem=True)
            rows.append({"operator": str(name or "Sem operador"), **metrics, "critical": int(group.get("is_critico", pd.Series(dtype="bool")).fillna(False).sum())})
        rows.sort(key=lambda item: (item["critical"], item["total_clientes"]), reverse=True)
        return {"items": rows, "total": len(rows)}

    def records(self, filters: dict[str, Any], page: int = 1, page_size: int = 100) -> dict[str, Any]:
        _, data = self._filtered(filters)
        page_size = max(25, min(int(page_size), 500))
        page = max(1, int(page))
        start = (page - 1) * page_size
        return {"items": self._records(data.iloc[start:start + page_size]), "total": len(data), "page": page, "page_size": page_size, "pages": max(1, (len(data) + page_size - 1) // page_size)}

    def report(
        self,
        filters: dict[str, Any],
        extension: str,
        snapshot_version: str = "",
    ) -> tuple[str, bytes]:
        snapshot = self._snapshot_by_version(snapshot_version)
        data = filter_dataframe(snapshot["data"], self._filter_values(filters))
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        if extension == "csv":
            return f"controle_defasagem_{stamp}.csv", to_csv_bytes(data)
        return f"controle_defasagem_{stamp}.xlsx", to_excel_bytes(data)
