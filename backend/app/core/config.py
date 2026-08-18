from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

BASE_DIR = Path(__file__).resolve().parent.parent.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=BASE_DIR / ".env", env_file_encoding="utf-8", extra="ignore"
    )

    app_name: str = "NAVBAT"
    debug: bool = False

    # sqlite by default; set to postgresql+asyncpg://... in production
    database_url: str = f"sqlite+aiosqlite:///{BASE_DIR / 'data' / 'navbat.db'}"

    secret_key: str = "change-me-in-production"
    access_token_expire_minutes: int = 60 * 24
    algorithm: str = "HS256"

    upload_dir: Path = BASE_DIR / "uploads"
    max_logo_size: int = 2 * 1024 * 1024  # 2 MB

    cors_origins: list[str] = ["http://localhost:5173", "http://127.0.0.1:5173"]

    # Telegram bots are started for companies that saved a token.
    # Disable globally (e.g. in tests / CI) with TELEGRAM_ENABLED=0.
    telegram_enabled: bool = True

    # Minutes a called client has to reach the desk (shown as countdown).
    call_timeout_minutes: int = 3


@lru_cache
def get_settings() -> Settings:
    return Settings()
