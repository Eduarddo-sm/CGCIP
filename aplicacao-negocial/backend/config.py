import secrets
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


def _persistent_jwt_secret() -> str:
    secret_path = Path(__file__).resolve().parents[1] / "database" / ".jwt_secret"
    try:
        if secret_path.exists():
            existing = secret_path.read_text(encoding="utf-8").strip()
            if len(existing) >= 48:
                return existing
        secret_path.parent.mkdir(parents=True, exist_ok=True)
        generated = secrets.token_urlsafe(64)
        secret_path.write_text(generated, encoding="utf-8")
        return generated
    except OSError:
        return secrets.token_urlsafe(64)


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    app_name: str = "Negocial Web"
    database_url: str = "sqlite:///database/negocial.sqlite3"
    jwt_secret_key: str = Field(default_factory=_persistent_jwt_secret)
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 480
    auth_cookie_name: str = "negocial_token"
    secure_cookies: bool = False
    admin_username: str = ""
    admin_password: str = ""
    log_level: str = "INFO"
    ferramenta_attachments_dir: str = ""


settings = Settings()
