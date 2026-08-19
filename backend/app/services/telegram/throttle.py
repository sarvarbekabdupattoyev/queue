"""Per-bot outbound rate limiting for Telegram.

Telegram caps a bot token at roughly 30 messages/second; a sale-day burst
(thousands of QR photos and queue notifications) fired unthrottled turns into
429 `retry_after` storms and silently lost messages. Every ``Bot`` gets ONE
:class:`RateLimitMiddleware` on its HTTP session, which makes it the single
choke point for everything that bot sends — FSM replies, QR photos and queue
notifications alike — per the repo rule that all Telegram-outbound traffic
goes through ``BotManager``-owned bots.

The limiter paces only ``send*`` API methods (the ones the per-bot cap
applies to); ``TelegramRetryAfter`` is obeyed and retried for every method so
a flood-control hiccup never drops a client's QR code. Clock and sleep are
injectable, so tests drive a fake clock and never really sleep.
"""

import asyncio
import logging
import time
from collections import deque
from collections.abc import Awaitable, Callable

from aiogram import Bot
from aiogram.client.session.middlewares.base import (
    BaseRequestMiddleware,
    NextRequestMiddlewareType,
)
from aiogram.exceptions import TelegramRetryAfter
from aiogram.methods import Response, TelegramMethod
from aiogram.methods.base import TelegramType

log = logging.getLogger(__name__)

# ~25 msg/s leaves headroom under Telegram's ~30 msg/s per-bot cap, so bursts
# ride the limit without triggering long flood bans.
MESSAGES_PER_SECOND = 25
RETRY_ATTEMPTS = 4

Clock = Callable[[], float]
Sleeper = Callable[[float], Awaitable[None]]


class SlidingWindowLimiter:
    """At most ``rate`` acquisitions per ``per`` seconds, FIFO-fair.

    Waiters queue on the internal lock, so a backlog drains at exactly the
    configured rate instead of stampeding when the window rolls over.
    """

    def __init__(
        self,
        rate: int = MESSAGES_PER_SECOND,
        per: float = 1.0,
        *,
        clock: Clock = time.monotonic,
        sleeper: Sleeper = asyncio.sleep,
    ) -> None:
        self.rate = rate
        self.per = per
        self._clock = clock
        self._sleep = sleeper
        self._stamps: deque[float] = deque()
        self._lock = asyncio.Lock()

    async def acquire(self) -> None:
        async with self._lock:
            while True:
                now = self._clock()
                while self._stamps and now - self._stamps[0] >= self.per:
                    self._stamps.popleft()
                if len(self._stamps) < self.rate:
                    self._stamps.append(now)
                    return
                await self._sleep(self.per - (now - self._stamps[0]))


class RateLimitMiddleware(BaseRequestMiddleware):
    """aiogram session middleware: pace sends, obey ``retry_after``."""

    def __init__(
        self,
        limiter: SlidingWindowLimiter | None = None,
        *,
        sleeper: Sleeper = asyncio.sleep,
    ) -> None:
        self.limiter = limiter or SlidingWindowLimiter()
        self._sleep = sleeper

    async def __call__(
        self,
        make_request: NextRequestMiddlewareType[TelegramType],
        bot: Bot,
        method: TelegramMethod[TelegramType],
    ) -> Response[TelegramType]:
        api_method = method.__api_method__
        paced = api_method.startswith("send")
        for attempt in range(1, RETRY_ATTEMPTS + 1):
            if paced:
                await self.limiter.acquire()
            try:
                return await make_request(bot, method)
            except TelegramRetryAfter as exc:
                if attempt == RETRY_ATTEMPTS:
                    raise
                log.warning(
                    "Flood control on %s (attempt %s/%s) — retrying in %ss",
                    api_method,
                    attempt,
                    RETRY_ATTEMPTS,
                    exc.retry_after,
                )
                await self._sleep(exc.retry_after + 1.0)
        raise AssertionError("unreachable")
