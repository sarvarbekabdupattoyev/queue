"""Multi-tenant Telegram bot supervisor.

Every company connects up to ``MAX_BOTS_PER_COMPANY`` bots (rows in
``company_bots``). All bots of a company run the SAME registration flow in
parallel — Telegram caps one bot at ~30 messages/second, so several bots
spread the load of a sale-day registration burst (up to ~10 000 sign-ups a
minute). This manager runs one runner per bot row — long polling by default,
or webhook mode when ``BOT_WEBHOOK_BASE`` is set (each bot registered at
``{base}/{bot_db_id}`` with a per-bot HMAC secret).

Deployment roles:

* single-process dev (no Redis): the API process embeds the manager and
  calls it directly.
* production (Redis set): only the dedicated bot service
  (``app.bot_main``) runs bots — API workers publish notifications and
  bot-change events to Redis, and this manager consumes them. That is what
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
from sqlalchemy import select, update

from app.core.config import get_settings
from app.core.redis import CH_BOT_CONTROL, CH_NOTIFY, get_redis
from app.services import i18n
from app.services.errors import DomainError
from app.services.telegram.throttle import RateLimitMiddleware

log = logging.getLogger(__name__)


def bot_commands(lang: str) -> list[BotCommand]:
    return [
        BotCommand(command="start", description=i18n.t(lang, "cmd_start_desc")),
        BotCommand(command="navbat", description=i18n.t(lang, "cmd_ticket_desc")),
        BotCommand(command="holat", description=i18n.t(lang, "cmd_status_desc")),
        BotCommand(command="info", description=i18n.t(lang, "cmd_info_desc")),
    ]


def webhook_secret(bot_db_id: int) -> str:
    """Per-bot webhook secret derived from SECRET_KEY (no schema change)."""
    settings = get_settings()
    digest = hmac.new(
        settings.secret_key.encode(), f"tgwh:bot:{bot_db_id}".encode(), hashlib.sha256
    ).hexdigest()
    return digest[:32]


async def validate_token(token: str) -> str | None:
    """Stateless token check (used by API workers that never run bots).
    Returns the bot username, None if Telegram is unreachable or disabled,
    and raises DomainError for a token Telegram rejects."""
    if not get_settings().telegram_enabled:
        return None
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
    def __init__(self, bot_db_id: int, company_id: int, token: str, storage: BaseStorage):
        self.bot_db_id = bot_db_id
        self.company_id = company_id
        self.token = token
        self.bot = Bot(token=token)
        # single choke point for EVERYTHING this bot sends: paces sends under
        # Telegram's per-token cap and retries on flood control (429)
        self.bot.session.middleware(RateLimitMiddleware())
        # company_id + bot_db_id land in workflow data, injected into handlers
        self.dp = Dispatcher(storage=storage, company_id=company_id, bot_db_id=bot_db_id)
        self.username: str | None = None
        self._polling_task: asyncio.Task | None = None

    async def start(self) -> str:
        from app.services.telegram.handlers import build_router

        settings = get_settings()
        me = await self.bot.get_me()
        self.username = me.username
        self.dp.include_router(build_router())
        with suppress(Exception):
            # Telegram shows the list matching the client's language; the
            # default (no language_code) is Uzbek
            await self.bot.set_my_commands(bot_commands(i18n.DEFAULT_LANG))
            for lang in ("ru", "en"):
                await self.bot.set_my_commands(bot_commands(lang), language_code=lang)

        if settings.bot_webhook_base:
            url = f"{settings.bot_webhook_base.rstrip('/')}/{self.bot_db_id}"
            await self.bot.set_webhook(
                url=url,
                secret_token=webhook_secret(self.bot_db_id),
                allowed_updates=self.dp.resolve_used_update_types(),
                drop_pending_updates=False,
                # default is 40 — 100 parallel connections lets Telegram
                # deliver a registration burst noticeably faster, for free
                max_connections=settings.bot_webhook_max_connections,
            )
            log.info("Bot @%s (company %s): webhook %s", me.username, self.company_id, url)
        else:
            await self.bot.delete_webhook(drop_pending_updates=False)
            self._polling_task = asyncio.create_task(
                self.dp.start_polling(
                    self.bot, handle_signals=False, close_bot_session=False
                ),
                name=f"tg-poll-bot-{self.bot_db_id}",
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
        log.info("Telegram bot %s stopped (company %s)", self.bot_db_id, self.company_id)


class BotManager:
    def __init__(self) -> None:
        # keyed by CompanyBot.id — one company may run several bots
        self._runners: dict[int, CompanyBotRunner] = {}
        self._storage: BaseStorage | None = None
        self._update_semaphore: asyncio.Semaphore | None = None

    @property
    def enabled(self) -> bool:
        return get_settings().telegram_enabled

    def is_running(self, bot_db_id: int) -> bool:
        return bot_db_id in self._runners

    def _get_storage(self) -> BaseStorage:
        """FSM storage shared by all dispatchers. RedisStorage keys include
        the Telegram bot id, so conversations survive restarts and neither
        tenants nor sibling bots of one company ever collide; MemoryStorage
        is the single-process fallback."""
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
        """Start a runner for every saved bot of every company."""
        if not self.enabled:
            return
        from app.db.session import SessionFactory
        from app.models import CompanyBot

        async with SessionFactory() as session:
            bots = (await session.scalars(select(CompanyBot))).all()
        for bot in bots:
            try:
                await self._start_runner(bot.id, bot.company_id, bot.token)
            except Exception as exc:  # one broken token must not sink the rest
                log.warning("Bot %s (company %s) failed to start: %s", bot.id, bot.company_id, exc)

    async def _start_runner(self, bot_db_id: int, company_id: int, token: str) -> str:
        runner = CompanyBotRunner(bot_db_id, company_id, token, self._get_storage())
        try:
            username = await runner.start()
        except Exception:
            await runner.bot.session.close()
            raise
        self._runners[bot_db_id] = runner
        # In multi-process mode this runs in the bot service, a different
        # process from the API request that saved the row -- if that
        # request's own validate_token() call missed (disabled at the
        # time, or a transient network blip returning None), the dashboard
        # would otherwise show "not started" forever for a bot that is, as
        # of this line, actually running. Keep the stored username honest.
        from app.db.session import SessionFactory
        from app.models import CompanyBot

        async with SessionFactory() as session:
            await session.execute(
                update(CompanyBot).where(CompanyBot.id == bot_db_id).values(username=username)
            )
            await session.commit()
        return username

    async def _stop_runner(self, bot_db_id: int) -> None:
        runner = self._runners.pop(bot_db_id, None)
        if runner is not None:
            await runner.stop()

    async def add_bot(self, bot_db_id: int, company_id: int, token: str) -> str | None:
        """Embedded mode: start a newly saved bot directly. Returns the bot
        username, or None when the bot could not start (disabled, network
        trouble). Raises DomainError for a bad token."""
        await self._stop_runner(bot_db_id)
        if not self.enabled:
            return None
        try:
            return await self._start_runner(bot_db_id, company_id, token)
        except TelegramUnauthorizedError:
            raise DomainError("Telegram bot tokeni yaroqsiz — BotFather'dan tekshiring") from None
        except TelegramNetworkError as exc:
            log.warning("Telegram unreachable while starting bot %s: %s", bot_db_id, exc)
            return None

    async def remove_bot(self, bot_db_id: int) -> None:
        """Embedded mode: stop a bot whose row was deleted."""
        await self._stop_runner(bot_db_id)

    async def reload_company(self, company_id: int) -> None:
        """Bot service: re-read the company's bots from the DB and converge
        (stop removed/changed runners, start missing ones)."""
        from app.db.session import SessionFactory
        from app.models import CompanyBot

        async with SessionFactory() as session:
            bots = (
                await session.scalars(
                    select(CompanyBot).where(CompanyBot.company_id == company_id)
                )
            ).all()
        wanted = {bot.id: bot for bot in bots}
        for bot_db_id, runner in list(self._runners.items()):
            if runner.company_id != company_id:
                continue
            bot = wanted.get(bot_db_id)
            if bot is None or bot.token != runner.token:
                await self._stop_runner(bot_db_id)
        if not self.enabled:
            return
        for bot in bots:
            if bot.id in self._runners:
                continue
            try:
                await self._start_runner(bot.id, company_id, bot.token)
            except Exception as exc:
                log.warning("Bot reload failed for bot %s (company %s): %s", bot.id, company_id, exc)

    async def stop_all(self) -> None:
        for bot_db_id in list(self._runners):
            with suppress(Exception):
                await self._stop_runner(bot_db_id)

    # -------------------------------------------------------------- webhooks ---

    async def feed_webhook(self, bot_db_id: int, secret: str, payload: dict) -> bool:
        """Accept a webhook update: ACK Telegram immediately, process in a
        semaphore-bounded background task so a 2000-update burst neither
        blocks the webhook endpoint nor floods the DB pool."""
        runner = self._runners.get(bot_db_id)
        if runner is None:
            return False
        if not hmac.compare_digest(secret, webhook_secret(bot_db_id)):
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
                    log.exception("Failed to process webhook update (bot %s)", bot_db_id)

        asyncio.get_running_loop().create_task(_process())
        return True

    # ----------------------------------------------------------- outbound API ---

    async def send_text(
        self, company_id: int, chat_id: int, text: str, bot_db_id: int | None = None
    ) -> None:
        """Best-effort notification to a client chat. Prefers the bot the
        client registered through; falls back to any running bot of the
        company (Telegram may still reject if the client never started it)."""
        runner = self._runners.get(bot_db_id) if bot_db_id is not None else None
        if runner is None or runner.company_id != company_id:
            runner = next(
                (r for r in self._runners.values() if r.company_id == company_id), None
            )
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
            lambda data: self.send_text(
                data["company_id"], data["chat_id"], data["text"], data.get("bot_id")
            ),
        )

    async def run_control_subscriber(self) -> None:
        """Bot service: react to bot changes made in the dashboard."""
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
