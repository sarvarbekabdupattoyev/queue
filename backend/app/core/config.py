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

    # sqlite for local development; postgresql+asyncpg://... in production
    database_url: str = f"sqlite+aiosqlite:///{BASE_DIR / 'data' / 'navbat.db'}"
    db_pool_size: int = 10
    db_max_overflow: int = 20

    # Redis switches the app into multi-process mode:
    #   empty  → single-process dev mode (embedded bots, in-memory WS rooms)
    #   set    → API workers ×N + separate bot service; WS fan-out, Telegram
    #            notifications and FSM state all go through Redis
    redis_url: str = ""

    secret_key: str = "change-me-in-production"
    access_token_expire_minutes: int = 60 * 24
    algorithm: str = "HS256"

    upload_dir: Path = BASE_DIR / "uploads"
    max_logo_size: int = 2 * 1024 * 1024  # 2 MB

    cors_origins: list[str] = ["http://localhost:5173", "http://127.0.0.1:5173"]

    # Telegram bots are started for companies that saved a token.
    # Disable globally (e.g. in tests / CI) with TELEGRAM_ENABLED=0.
    telegram_enabled: bool = True

    # Webhook mode for the bot service. Empty → long polling (dev / simple
    # deployments). Set to the public base URL routed to the bot service,
    # e.g. https://example.com/tgwh — each bot is registered at
    # {base}/{company_id} with a per-company secret token.
    bot_webhook_base: str = ""
    # Max updates processed concurrently by the bot service (protects the
    # DB pool during registration bursts).
    bot_max_concurrent_updates: int = 64

    # Full event state is rebuilt and pushed to screens at most once per
    # window, however many mutations land inside it.
    broadcast_debounce_ms: int = 200

    # Minutes a called client has to reach the desk (shown as countdown).
    call_timeout_minutes: int = 3

    @property
    def multi_process(self) -> bool:
        return bool(self.redis_url)


@lru_cache
def get_settings() -> Settings:
    return Settings()
