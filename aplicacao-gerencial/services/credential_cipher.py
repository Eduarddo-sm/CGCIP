from __future__ import annotations

import os
from pathlib import Path

from cryptography.fernet import Fernet, InvalidToken


PREFIX = "enc:v1:"


class CredentialCipher:
    def __init__(self) -> None:
        configured = os.environ.get("SPREADSHEET_CREDENTIAL_KEY", "").strip()
        key = configured.encode("ascii") if configured else self._local_key()
        self._fernet = Fernet(key)

    def encrypt(self, value: str | None) -> str | None:
        raw = str(value or "")
        if not raw:
            return None
        if raw.startswith(PREFIX):
            return raw
        token = self._fernet.encrypt(raw.encode("utf-8")).decode("ascii")
        return f"{PREFIX}{token}"

    def decrypt(self, value: str | None) -> str | None:
        raw = str(value or "")
        if not raw:
            return None
        if not raw.startswith(PREFIX):
            return raw
        try:
            return self._fernet.decrypt(raw[len(PREFIX):].encode("ascii")).decode("utf-8")
        except InvalidToken as exc:
            raise RuntimeError("Nao foi possivel descriptografar a credencial da planilha.") from exc

    @staticmethod
    def _local_key() -> bytes:
        path = Path(__file__).resolve().parents[1] / "data" / ".spreadsheet_credential_key"
        if path.exists():
            return path.read_bytes().strip()
        path.parent.mkdir(parents=True, exist_ok=True)
        key = Fernet.generate_key()
        path.write_bytes(key)
        return key
