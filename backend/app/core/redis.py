"""Shared async Redis client.

Redis is optional: when ``REDIS_URL`` is empty the app runs in single-process
mode and every consumer of :func:`get_redis` must handle ``None``.
"""

import logging

from redis.asyncio import Redis

from app.core.config import get_settings

log = logging.getLogger(__name__)

# pub/sub channels
CH_WS = "navbat:ws"                 # WS state fan-out between API workers
CH_NOTIFY = "navbat:tg-notify"      # API → bot service: send a Telegram message
CH_BOT_CONTROL = "navbat:tg-ctl"    # API → bot service: company token changed

_client: Redis | None = None


def get_redis() -> Redis | None:
    global _client
    if _client is None:
        settings = get_settings()
        if not settings.redis_url:
            return None
        _client = Redis.from_url(
            settings.redis_url,
            encoding="utf-8",
            decode_responses=True,
            socket_keepalive=True,
            health_check_interval=30,
        )
    return _client


async def close_redis() -> None:
    global _client
    if _client is not None:
        try:
            await _client.aclose()
        except Exception:  # pragma: no cover - best-effort shutdown
            pass
        _client = None
