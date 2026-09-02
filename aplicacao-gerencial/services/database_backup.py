from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import threading
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib.parse import unquote, urlparse


class DatabaseBackupService:
    def __init__(self, database_url: str, data_dir: Path) -> None:
        self.database_url = database_url
        self.data_dir = Path(data_dir)
        self.default_backup_dir = self.data_dir / "backups" / "database"
        self.config_path = self.data_dir / "backup_storage.json"
        self.backup_dir = self._configured_backup_dir()
        if self.backup_dir == self.default_backup_dir:
            self.backup_dir.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()

    def storage_config(self) -> dict[str, Any]:
        path = self.backup_dir
        return {
            "path": str(path),
            "default_path": str(self.default_backup_dir),
            "custom": path.resolve() != self.default_backup_dir.resolve(),
            "available": path.is_dir(),
            "writable": path.is_dir() and os.access(path, os.W_OK),
        }

    def configure_storage(self, path: str, migrate_existing: bool = False) -> dict[str, Any]:
        raw_path = os.path.expandvars(os.path.expanduser(str(path or "").strip().strip('"')))
        target = Path(raw_path) if raw_path else self.default_backup_dir
        if not target.is_absolute():
            raise RuntimeError("Informe um caminho absoluto para os backups.")
        try:
            target.mkdir(parents=True, exist_ok=True)
            probe = target / f".backup-write-test-{os.getpid()}-{threading.get_ident()}"
            probe.write_text("ok", encoding="utf-8")
            probe.unlink(missing_ok=True)
        except OSError as exc:
            raise RuntimeError(f"O diretorio de backup nao pode ser utilizado: {exc}") from exc

        with self._lock:
            previous = self.backup_dir
            moved = 0
            if migrate_existing and previous.resolve() != target.resolve() and previous.is_dir():
                for source in previous.glob("*.dump"):
                    destination = target / source.name
                    if destination.exists():
                        raise RuntimeError(f"Ja existe um backup com o nome {source.name} no novo destino.")
                    shutil.move(str(source), str(destination))
                    moved += 1
            self.backup_dir = target
            self._save_storage_config(target)
        return {"ok": True, "storage": self.storage_config(), "moved_backups": moved}

    def list_backups(self) -> dict[str, Any]:
        self._ensure_backup_dir()
        items = []
        for file_path in sorted(self.backup_dir.glob("*.dump"), key=lambda item: item.stat().st_mtime, reverse=True):
            stat = file_path.stat()
            items.append({
                "name": file_path.name,
                "path": str(file_path),
                "size_bytes": stat.st_size,
                "created_at": datetime.fromtimestamp(stat.st_mtime).isoformat(timespec="seconds"),
                "source": self._backup_source(file_path.name),
            })
        return {"ok": True, "items": items}

    def create_backup(
        self,
        prefix: str = "projeto_negocial",
        snapshot: str | None = None,
        protected_names: set[str] | None = None,
    ) -> dict[str, Any]:
        with self._lock:
            self._ensure_backup_dir()
            pg_dump = self._require_binary("pg_dump")
            safe_prefix = "".join(char for char in str(prefix or "projeto_negocial") if char.isalnum() or char in {"_", "-"}).strip("_-")
            target = self.backup_dir / f"{safe_prefix or 'projeto_negocial'}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.dump"
            parsed = self._parsed()
            command = [
                pg_dump,
                "--format=custom",
                "--file",
                str(target),
                "--host",
                parsed["host"],
                "--port",
                parsed["port"],
                "--username",
                parsed["username"],
                parsed["database"],
            ]
            if snapshot:
                command.insert(-1, f"--snapshot={snapshot}")
            try:
                self._run(command, parsed)
                size_bytes = target.stat().st_size
                checksum = self._sha256(target)
            except Exception:
                target.unlink(missing_ok=True)
                raise

            deleted_backup = self._delete_oldest_backup(
                protected_names={target.name, *(protected_names or set())},
            )
            return {
                "ok": True,
                "backup": {
                    "name": target.name,
                    "path": str(target),
                    "size_bytes": size_bytes,
                    "sha256": checksum,
                },
                "deleted_backup": deleted_backup,
            }

    def restore_backup(self, backup_name: str) -> dict[str, Any]:
        self._ensure_backup_dir()
        pg_restore = self._require_binary("pg_restore")
        target = self._backup_path(backup_name)
        with self._lock:
            pre_restore = self.create_backup("pre_restore", protected_names={target.name})
            parsed = self._parsed()
            command = [
                pg_restore,
                "--clean",
                "--if-exists",
                "--no-owner",
                "--host",
                parsed["host"],
                "--port",
                parsed["port"],
                "--username",
                parsed["username"],
                "--dbname",
                parsed["database"],
                str(target),
            ]
            self._run(command, parsed)
            return {"ok": True, "restored": target.name, "pre_restore_backup": pre_restore.get("backup")}

    def verify_backup(self, backup_name: str) -> dict[str, Any]:
        self._ensure_backup_dir()
        target = self._backup_path(backup_name)
        pg_restore = self._require_binary("pg_restore")
        with self._lock:
            self._run([pg_restore, "--list", str(target)], self._parsed())
            stat = target.stat()
            return {
                "ok": True,
                "name": target.name,
                "size_bytes": stat.st_size,
                "sha256": self._sha256(target),
                "verified_at": datetime.now().isoformat(timespec="seconds"),
            }

    def _delete_oldest_backup(self, protected_names: set[str] | None = None) -> dict[str, Any] | None:
        protected = {Path(name).name for name in (protected_names or set())}
        candidates = [
            file_path
            for file_path in self.backup_dir.glob("*.dump")
            if file_path.name not in protected
        ]
        if not candidates:
            return None
        oldest = min(candidates, key=lambda item: (item.stat().st_mtime, item.name))
        stat = oldest.stat()
        deleted = {
            "name": oldest.name,
            "path": str(oldest),
            "size_bytes": stat.st_size,
            "created_at": datetime.fromtimestamp(stat.st_mtime).isoformat(timespec="seconds"),
        }
        oldest.unlink()
        return deleted

    def _configured_backup_dir(self) -> Path:
        try:
            payload = json.loads(self.config_path.read_text(encoding="utf-8"))
            configured = str(payload.get("path") or "").strip() if isinstance(payload, dict) else ""
        except (OSError, json.JSONDecodeError):
            configured = ""
        return Path(configured) if configured else self.default_backup_dir

    def _save_storage_config(self, target: Path) -> None:
        self.config_path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.config_path.with_suffix(".tmp")
        temporary.write_text(
            json.dumps({"path": str(target), "updated_at": datetime.now().isoformat(timespec="seconds")}, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        temporary.replace(self.config_path)

    def _ensure_backup_dir(self) -> None:
        try:
            self.backup_dir.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            raise RuntimeError(f"Diretorio de backup indisponivel: {self.backup_dir}. {exc}") from exc

    def _backup_path(self, backup_name: str) -> Path:
        target = (self.backup_dir / Path(backup_name).name).resolve()
        root = self.backup_dir.resolve()
        if root not in target.parents or not target.exists() or target.suffix.lower() != ".dump":
            raise RuntimeError("Backup invalido.")
        return target

    @staticmethod
    def _backup_source(name: str) -> str:
        normalized = str(name or "").lower()
        if normalized.startswith("automatico_"):
            return "automatic"
        if normalized.startswith("pre_restore_"):
            return "pre_restore"
        return "manual"

    def _parsed(self) -> dict[str, str]:
        url = self.database_url.replace("postgresql+psycopg://", "postgresql://", 1)
        parsed = urlparse(url)
        if not parsed.hostname or not parsed.username or not parsed.path:
            raise RuntimeError("DATABASE_URL invalida para backup.")
        return {
            "host": parsed.hostname,
            "port": str(parsed.port or 5432),
            "username": unquote(parsed.username),
            "password": unquote(parsed.password or ""),
            "database": parsed.path.lstrip("/"),
        }

    def _require_binary(self, name: str) -> str:
        binary = shutil.which(name)
        if binary:
            return binary
        if os.name == "nt":
            candidates: list[Path] = []
            for env_name in ("ProgramFiles", "ProgramFiles(x86)"):
                program_files = os.environ.get(env_name, "").strip()
                if not program_files:
                    continue
                postgres_root = Path(program_files) / "PostgreSQL"
                if postgres_root.exists():
                    candidates.extend(postgres_root.glob(f"*\\bin\\{name}.exe"))
            if candidates:
                def version_key(path: Path) -> tuple[int, ...]:
                    try:
                        return tuple(int(part) for part in path.parents[1].name.split("."))
                    except ValueError:
                        return (0,)
                return str(sorted(candidates, key=version_key, reverse=True)[0])
        raise RuntimeError(
            f"{name} nao encontrado. Instale PostgreSQL tools ou configure o PATH do servidor."
        )

    def _run(self, command: list[str], parsed: dict[str, str]) -> None:
        env = os.environ.copy()
        if parsed.get("password"):
            env["PGPASSWORD"] = parsed["password"]
        result = subprocess.run(command, env=env, capture_output=True, text=True, timeout=600)
        if result.returncode != 0:
            raise RuntimeError((result.stderr or result.stdout or "Falha no comando de backup.").strip())

    @staticmethod
    def _sha256(path: Path) -> str:
        digest = hashlib.sha256()
        with path.open("rb") as stream:
            for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(chunk)
        return digest.hexdigest()
