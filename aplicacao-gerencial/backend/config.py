from __future__ import annotations

import os
import sys
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import unquote, urlparse


ROOT = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parents[1]))


def _load_env_file(path: Path) -> None:
    if not path.exists():
        return
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        os.environ.setdefault(key, value)


_load_env_file(ROOT / ".env")


def _default_data_dir() -> Path:
    return Path(os.environ.get("NEGOCIADORES_DATA_DIR", ROOT / "data"))


def _default_database_url() -> str:
    return f"sqlite:///{(_default_data_dir() / 'app.sqlite3').as_posix()}"


def sqlite_path_from_url(database_url: str) -> Path:
    parsed = urlparse(database_url)
    if parsed.scheme != "sqlite":
        raise ValueError(f"Banco ainda nao suportado pelo gerencial nesta etapa: {parsed.scheme}")

    if parsed.netloc and parsed.netloc != "":
        raise ValueError("Use sqlite:///caminho/do/banco.sqlite3 para configurar SQLite.")

    raw_path = unquote(parsed.path)
    if raw_path.startswith("/") and len(raw_path) > 3 and raw_path[2] == ":":
        raw_path = raw_path[1:]

    path = Path(raw_path)
    if not path.is_absolute():
        path = ROOT / path
    return path


@dataclass(frozen=True)
class Settings:
    ui_dir: Path
    data_dir: Path
    database_url: str
    secure_cookies: bool

    @property
    def database_backend(self) -> str:
        return urlparse(self.database_url).scheme

    @property
    def sqlite_path(self) -> Path:
        return sqlite_path_from_url(self.database_url)


settings = Settings(
    ui_dir=Path(os.environ.get("NEGOCIADORES_UI_DIR", ROOT / "ui")),
    data_dir=_default_data_dir(),
    database_url=os.environ.get("DATABASE_URL", _default_database_url()),
    secure_cookies=os.environ.get("SECURE_COOKIES", "false").strip().lower() in {"1", "true", "yes", "sim"},
)
