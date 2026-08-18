"""Multi-tenant Telegram bot supervisor.

Every company stores its own bot token. This manager runs one runner per
configured company — long polling by default, or webhook mode when
``BOT_WEBHOOK_BASE`` is set (each bot registered at ``{base}/{company_id}``
with a per-company HMAC secret).

Deployment roles:

* single-process dev (no Redis): the API process embeds the manager and
  calls it directly.
* production (Redis set): only the dedicated bot service
  (``app.bot_main``) runs bots — API workers publish notifications and
  token-change events to Redis, and this manager consumes them. That is what
  makes ``uvicorn --workers N`` safe (no per-worker polling → no 409s).
"""

import asyncio
import hashlib
import hmac
import json
import logging
from contextlib import suppress

from aiogram import Bot, Dispatcher
from aiogram.exceptions import TelegramNetworkError, TelegramUnauthorizedError
from aiogram.fsm.storage.base import BaseStorage
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.fsm.storage.redis import DefaultKeyBuilder, RedisStorage
from aiogram.types import BotCommand, Update
from sqlalchemy import select

from app.core.config import get_settings
from app.core.redis import CH_BOT_CONTROL, CH_NOTIFY, get_redis
from app.services.errors import DomainError

log = logging.getLogger(__name__)

BOT_COMMANDS = [
    BotCommand(command="start", description="Ro'yxatdan o'tish"),
    BotCommand(command="navbat", description="Mening navbatim (QR-kod)"),
    BotCommand(command="holat", description="Navbat holati"),
]


def webhook_secret(company_id: int) -> str:
    """Per-company webhook secret derived from SECRET_KEY (no schema change)."""
    settings = get_settings()
    digest = hmac.new(
        settings.secret_key.encode(), f"tgwh:{company_id}".encode(), hashlib.sha256
    ).hexdigest()
    return digest[:32]


async def validate_token(token: str) -> str | None:
    """Stateless token check (used by API workers that never run bots).
    Returns the bot username, None if Telegram is unreachable, and raises
    DomainError for a token Telegram rejects."""
    bot = Bot(token=token)
    try:
        me = await bot.get_me()
        return me.username
    except TelegramUnauthorizedError:
        raise DomainError("Telegram bot tokeni yaroqsiz — BotFather'dan tekshiring") from None
    except TelegramNetworkError as exc:
        log.warning("Telegram unreachable while validating token: %s", exc)
        return None
    finally:
        await bot.session.close()


class CompanyBotRunner:
    def __init__(self, company_id: int, token: str, storage: BaseStorage):
        self.company_id = company_id
        self.token = token
        self.bot = Bot(token=token)
        # company_id lands in workflow data and is injected into handlers
        self.dp = Dispatcher(storage=storage, company_id=company_id)
        self.username: str | None = None
        self._polling_task: asyncio.Task | None = None

    async def start(self) -> str:
        from app.services.telegram.handlers import build_router

        settings = get_settings()
        me = await self.bot.get_me()
        self.username = me.username
        self.dp.include_router(build_router())
        with suppress(Exception):
            await self.bot.set_my_commands(BOT_COMMANDS)

        if settings.bot_webhook_base:
            url = f"{settings.bot_webhook_base.rstrip('/')}/{self.company_id}"
            await self.bot.set_webhook(
                url=url,
                secret_token=webhook_secret(self.company_id),
                allowed_updates=self.dp.resolve_used_update_types(),
                drop_pending_updates=False,
            )
            log.info("Bot @%s (company %s): webhook %s", me.username, self.company_id, url)
        else:
            await self.bot.delete_webhook(drop_pending_updates=False)
            self._polling_task = asyncio.create_task(
                self.dp.start_polling(
                    self.bot, handle_signals=False, close_bot_session=False
                ),
                name=f"tg-poll-company-{self.company_id}",
            )
            log.info("Bot @%s (company %s): polling", me.username, self.company_id)
        return me.username

    async def feed_update(self, payload: dict) -> None:
        update = Update.model_validate(payload, context={"bot": self.bot})
        await self.dp.feed_update(self.bot, update)

    async def stop(self) -> None:
        if self._polling_task is not None:
            with suppress(RuntimeError):
                await self.dp.stop_polling()
            self._polling_task.cancel()
            with suppress(asyncio.CancelledError, Exception):
                await self._polling_task
        elif get_settings().bot_webhook_base:
            # token removed/replaced: stop Telegram from calling our webhook
            with suppress(Exception):
                await self.bot.delete_webhook(drop_pending_updates=False)
        await self.bot.session.close()
        log.info("Telegram bot stopped for company %s", self.company_id)


class BotManager:
    def __init__(self) -> None:
        self._runners: dict[int, CompanyBotRunner] = {}
        self._storage: BaseStorage | None = None
        self._update_semaphore: asyncio.Semaphore | None = None

    @property
    def enabled(self) -> bool:
        return get_settings().telegram_enabled

    def is_running(self, company_id: int) -> bool:
        return company_id in self._runners

    def _get_storage(self) -> BaseStorage:
        """FSM storage shared by all company dispatchers. RedisStorage keys
        include the bot id, so conversations survive restarts and tenants
        never collide; MemoryStorage is the single-process fallback."""
        if self._storage is None:
            redis = get_redis()
            if redis is not None:
                self._storage = RedisStorage(
                    redis=redis,
                    key_builder=DefaultKeyBuilder(with_bot_id=True),
                    state_ttl=6 * 3600,
                    data_ttl=6 * 3600,
                )
            else:
                self._storage = MemoryStorage()
        return self._storage

    # ------------------------------------------------------------- lifecycle ---

    async def start_all(self) -> None:
        """Start bots for every company with a saved token."""
        if not self.enabled:
            return
        from app.db.session import SessionFactory
        from app.models import Company

        async with SessionFactory() as session:
            companies = (
                await session.scalars(
                    select(Company).where(Company.telegram_bot_token.is_not(None))
                )
            ).all()
        for company in companies:
            try:
                await self._start_runner(company.id, company.telegram_bot_token)
            except Exception as exc:  # one broken token must not sink the rest
                log.warning("Bot for company %s failed to start: %s", company.id, exc)

    async def _start_runner(self, company_id: int, token: str) -> str:
        runner = CompanyBotRunner(company_id, token, self._get_storage())
        try:
            username = await runner.start()
        except Exception:
            await runner.bot.session.close()
            raise
        self._runners[company_id] = runner
        return username

    async def _stop_runner(self, company_id: int) -> None:
        runner = self._runners.pop(company_id, None)
        if runner is not None:
            await runner.stop()

    async def set_token(self, company_id: int, token: str | None) -> str | None:
        """Embedded mode: apply a token change directly. Returns the bot
        username, or None when the bot could not start (cleared token,
        disabled, network trouble). Raises DomainError for a bad token."""
        await self._stop_runner(company_id)
        if not token or not self.enabled:
            return None
        try:
            return await self._start_runner(company_id, token)
        except TelegramUnauthorizedError:
            raise DomainError("Telegram bot tokeni yaroqsiz — BotFather'dan tekshiring") from None
        except TelegramNetworkError as exc:
            log.warning("Telegram unreachable while starting bot for company %s: %s", company_id, exc)
            return None

    async def reload_company(self, company_id: int) -> None:
        """Bot service: re-read the company's token from the DB and converge."""
        from app.db.session import SessionFactory
        from app.models import Company

        async with SessionFactory() as session:
            company = await session.get(Company, company_id)
        token = company.telegram_bot_token if company else None
        current = self._runners.get(company_id)
        if current is not None and current.token == token:
            return
        await self._stop_runner(company_id)
        if token and self.enabled:
            try:
                await self._start_runner(company_id, token)
            except Exception as exc:
                log.warning("Bot reload failed for company %s: %s", company_id, exc)

    async def stop_all(self) -> None:
        for company_id in list(self._runners):
            with suppress(Exception):
                await self._stop_runner(company_id)

    # -------------------------------------------------------------- webhooks ---

    async def feed_webhook(self, company_id: int, secret: str, payload: dict) -> bool:
        """Accept a webhook update: ACK Telegram immediately, process in a
        semaphore-bounded background task so a 2000-update burst neither
        blocks the webhook endpoint nor floods the DB pool."""
        runner = self._runners.get(company_id)
        if runner is None:
            return False
        if not hmac.compare_digest(secret, webhook_secret(company_id)):
            return False
        if self._update_semaphore is None:
            self._update_semaphore = asyncio.Semaphore(
                get_settings().bot_max_concurrent_updates
            )

        async def _process() -> None:
            async with self._update_semaphore:
                try:
                    await runner.feed_update(payload)
                except Exception:
                    log.exception("Failed to process webhook update (company %s)", company_id)

        asyncio.get_running_loop().create_task(_process())
        return True

    # ----------------------------------------------------------- outbound API ---

    async def send_text(self, company_id: int, chat_id: int, text: str) -> None:
        """Best-effort notification to a client chat."""
        runner = self._runners.get(company_id)
        if runner is None:
            log.debug("No running bot for company %s; message dropped", company_id)
            return
        try:
            await runner.bot.send_message(chat_id, text)
        except Exception as exc:
            log.warning("Failed to notify chat %s (company %s): %s", chat_id, company_id, exc)

    # ------------------------------------------------------ redis subscribers ---

    async def run_notify_subscriber(self) -> None:
        """Bot service: deliver notifications published by API workers."""
        await self._subscribe_loop(
            CH_NOTIFY,
            lambda data: self.send_text(data["company_id"], data["chat_id"], data["text"]),
        )

    async def run_control_subscriber(self) -> None:
        """Bot service: react to token changes made in the dashboard."""
        await self._subscribe_loop(
            CH_BOT_CONTROL, lambda data: self.reload_company(data["company_id"])
        )

    async def _subscribe_loop(self, channel: str, handler) -> None:
        delay = 1.0
        while True:
            redis = get_redis()
            if redis is None:
                return
            try:
                pubsub = redis.pubsub()
                await pubsub.subscribe(channel)
                delay = 1.0
                async for item in pubsub.listen():
                    if item.get("type") != "message":
                        continue
                    try:
                        data = json.loads(item["data"])
                        asyncio.get_running_loop().create_task(handler(data))
                    except Exception:
                        log.exception("Bad message on %s", channel)
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                log.warning("%s subscriber lost Redis (%s); retry in %.0fs", channel, exc, delay)
                await asyncio.sleep(delay)
                delay = min(delay * 2, 15.0)


bot_manager = BotManager()
