from __future__ import annotations

import json
import os
import shutil
import threading
from datetime import datetime
from pathlib import Path
from typing import Any


class AttachmentStorageService:
    """Configures the shared filesystem used by dynamic-tool attachments."""

    def __init__(self) -> None:
        self.shared_data_dir = Path(__file__).resolve().parents[2] / "data"
        self.default_dir = self.shared_data_dir / "ferramenta-anexos"
        self.config_path = self.shared_data_dir / "ferramenta_attachment_storage.json"
        self._lock = threading.RLock()

    def storage_config(self) -> dict[str, Any]:
        payload = self._read_config()
        current = self._current_path(payload)
        legacy = self._legacy_paths(payload, current)
        files, size_bytes = self._usage([current, *legacy])
        return {
            "path": str(current),
            "default_path": str(self.default_dir),
            "custom": current != self.default_dir.resolve(),
            "available": current.is_dir(),
            "writable": current.is_dir() and os.access(current, os.W_OK),
            "legacy_paths": [str(item) for item in legacy],
            "files": files,
            "size_bytes": size_bytes,
        }

    def configure_storage(self, path: str, migrate_existing: bool = True) -> dict[str, Any]:
        raw_path = os.path.expandvars(os.path.expanduser(str(path or "").strip().strip('"')))
        target = Path(raw_path) if raw_path else self.default_dir
        if not target.is_absolute():
            raise RuntimeError("Informe um caminho absoluto para os arquivos anexados.")
        target = target.resolve()
        self._validate_target(target)

        with self._lock:
            previous_payload = self._read_config()
            previous = self._current_path(previous_payload)
            previous_roots = [previous, *self._legacy_paths(previous_payload, previous)]
            if any(root != target and root in target.parents for root in previous_roots):
                raise RuntimeError("O novo destino nao pode ficar dentro do diretorio de anexos atual.")
            moved = 0
            legacy: list[Path] = []
            if target != previous:
                if migrate_existing:
                    moved = self._copy_existing(previous_roots, target)
                else:
                    legacy = [item for item in previous_roots if item != target and item.is_dir()]
            elif not migrate_existing:
                legacy = self._legacy_paths(previous_payload, previous)

            self._save_config(target, legacy)
            if migrate_existing:
                self._remove_migrated_files(previous_roots, target)

        return {
            "ok": True,
            "storage": self.storage_config(),
            "moved_attachments": moved,
        }

    def _read_config(self) -> dict[str, Any]:
        try:
            payload = json.loads(self.config_path.read_text(encoding="utf-8"))
            return payload if isinstance(payload, dict) else {}
        except (OSError, json.JSONDecodeError):
            return {}

    def _current_path(self, payload: dict[str, Any]) -> Path:
        configured = str(payload.get("path") or os.environ.get("FERRAMENTA_ATTACHMENTS_DIR") or "").strip()
        return (Path(configured).expanduser() if configured else self.default_dir).resolve()

    @staticmethod
    def _legacy_paths(payload: dict[str, Any], current: Path) -> list[Path]:
        result: list[Path] = []
        for raw in payload.get("legacy_paths") or []:
            try:
                path = Path(str(raw)).expanduser().resolve()
            except (OSError, ValueError):
                continue
            if path != current and path not in result:
                result.append(path)
        return result

    def _validate_target(self, target: Path) -> None:
        try:
            target.mkdir(parents=True, exist_ok=True)
            probe = target / f".attachment-write-test-{os.getpid()}-{threading.get_ident()}"
            probe.write_text("ok", encoding="utf-8")
            probe.unlink(missing_ok=True)
        except OSError as exc:
            raise RuntimeError(f"O diretorio de anexos nao pode ser utilizado: {exc}") from exc

    def _save_config(self, target: Path, legacy: list[Path]) -> None:
        self.config_path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.config_path.with_suffix(".tmp")
        temporary.write_text(
            json.dumps({
                "path": str(target),
                "legacy_paths": [str(item) for item in legacy],
                "updated_at": datetime.now().isoformat(timespec="seconds"),
            }, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        temporary.replace(self.config_path)

    @staticmethod
    def _usage(roots: list[Path]) -> tuple[int, int]:
        files = 0
        size_bytes = 0
        seen: set[Path] = set()
        for root in roots:
            if not root.is_dir():
                continue
            for item in root.rglob("*"):
                if not item.is_file():
                    continue
                resolved = item.resolve()
                if resolved in seen:
                    continue
                seen.add(resolved)
                files += 1
                try:
                    size_bytes += item.stat().st_size
                except OSError:
                    pass
        return files, size_bytes

    @staticmethod
    def _copy_existing(roots: list[Path], target: Path) -> int:
        copied = 0
        created: list[Path] = []
        try:
            for root in roots:
                if not root.is_dir() or root.resolve() == target:
                    continue
                for source in root.rglob("*"):
                    if not source.is_file():
                        continue
                    relative = source.relative_to(root)
                    destination = target / relative
                    if destination.exists():
                        if destination.read_bytes() == source.read_bytes():
                            continue
                        raise RuntimeError(f"Ja existe um arquivo diferente no novo destino: {relative}.")
                    destination.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(source, destination)
                    created.append(destination)
                    copied += 1
            return copied
        except Exception:
            for item in reversed(created):
                item.unlink(missing_ok=True)
            raise

    @staticmethod
    def _remove_migrated_files(roots: list[Path], target: Path) -> None:
        for root in roots:
            if not root.is_dir() or root.resolve() == target:
                continue
            for source in root.rglob("*"):
                if source.is_file() and (target / source.relative_to(root)).is_file():
                    source.unlink(missing_ok=True)
            for directory in sorted((item for item in root.rglob("*") if item.is_dir()), reverse=True):
                try:
                    directory.rmdir()
                except OSError:
                    pass
