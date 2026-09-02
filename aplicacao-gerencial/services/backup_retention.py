from __future__ import annotations

import json
import re
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any


DEFAULT_POLICY = {
    "enabled": True,
    "retention_days": 90,
    "keep_latest_per_source": 200,
    "database_retention_days": 90,
    "database_keep_latest": 30,
    "extensions": [".xlsx", ".xlsm", ".xls", ".dump"],
}


class BackupRetentionService:
    TIMESTAMP_RE = re.compile(r"_(\d{8})_(\d{6})$")

    def __init__(self, data_dir: Path) -> None:
        self.data_dir = data_dir
        self.backup_dir = data_dir / "backups"
        self.config_path = data_dir / "backup_retention.json"
        self.backup_dir.mkdir(exist_ok=True)
        if not self.config_path.exists():
            self.save_policy(DEFAULT_POLICY)

    def policy(self) -> dict[str, Any]:
        try:
            loaded = json.loads(self.config_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            loaded = {}
        policy = DEFAULT_POLICY | (loaded if isinstance(loaded, dict) else {})
        policy["retention_days"] = max(1, int(policy.get("retention_days") or DEFAULT_POLICY["retention_days"]))
        policy["keep_latest_per_source"] = max(1, int(policy.get("keep_latest_per_source") or DEFAULT_POLICY["keep_latest_per_source"]))
        policy["database_retention_days"] = max(1, int(policy.get("database_retention_days") or DEFAULT_POLICY["database_retention_days"]))
        policy["database_keep_latest"] = max(1, int(policy.get("database_keep_latest") or DEFAULT_POLICY["database_keep_latest"]))
        configured_extensions = [str(ext).lower() for ext in policy.get("extensions") or []]
        policy["extensions"] = sorted(set(DEFAULT_POLICY["extensions"]) | set(configured_extensions))
        policy["enabled"] = bool(policy.get("enabled"))
        return policy

    def save_policy(self, payload: dict[str, Any]) -> dict[str, Any]:
        policy = DEFAULT_POLICY | (payload or {})
        self.config_path.write_text(json.dumps(policy, ensure_ascii=False, indent=2), encoding="utf-8")
        return self.policy()

    def cleanup(self, dry_run: bool = False) -> dict[str, Any]:
        policy = self.policy()
        if not policy["enabled"] and not dry_run:
            return {"ok": True, "enabled": False, "deleted": [], "kept": 0, "candidates": 0}

        files = self._backup_files(policy["extensions"])
        grouped = self._group_by_source(files)
        deleted: list[dict[str, Any]] = []
        candidates = 0
        kept = 0

        for source_files in grouped.values():
            source_files.sort(key=lambda item: item.stat().st_mtime, reverse=True)
            is_database = any(file_path.suffix.lower() == ".dump" for file_path in source_files)
            keep_latest = policy["database_keep_latest"] if is_database else policy["keep_latest_per_source"]
            retention_days = policy["database_retention_days"] if is_database else policy["retention_days"]
            cutoff = datetime.now() - timedelta(days=retention_days)
            protected = set(source_files[:keep_latest])
            for file_path in source_files:
                file_time = datetime.fromtimestamp(file_path.stat().st_mtime)
                if file_path in protected or file_time >= cutoff:
                    kept += 1
                    continue
                candidates += 1
                deleted.append({"path": str(file_path), "last_write": file_time.isoformat(timespec="seconds")})
                if not dry_run:
                    file_path.unlink(missing_ok=True)

        return {
            "ok": True,
            "enabled": policy["enabled"],
            "dry_run": dry_run,
            "deleted": deleted,
            "kept": kept,
            "candidates": candidates,
            "policy": policy,
        }

    def _backup_files(self, extensions: list[str]) -> list[Path]:
        root = self.backup_dir.resolve()
        result = []
        for file_path in self.backup_dir.rglob("*"):
            if not file_path.is_file() or file_path.suffix.lower() not in extensions:
                continue
            resolved = file_path.resolve()
            if root not in resolved.parents and resolved != root:
                continue
            result.append(file_path)
        return result

    def _group_by_source(self, files: list[Path]) -> dict[str, list[Path]]:
        grouped: dict[str, list[Path]] = {}
        for file_path in files:
            source = self.TIMESTAMP_RE.sub("", file_path.stem)
            grouped.setdefault(source, []).append(file_path)
        return grouped
