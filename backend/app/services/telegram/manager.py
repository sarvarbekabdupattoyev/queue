"""Multi-tenant Telegram bot supervisor.

Every company stores its own bot token; this manager runs one aiogram polling
task per configured company and restarts/stops runners when tokens change.
"""

import asyncio
import logging
from contextlib import suppress

from aiogram import Bot, Dispatcher
from aiogram.exceptions import TelegramNetworkError, TelegramUnauthorizedError
from aiogram.fsm.storage.memory import MemoryStorage
from sqlalchemy import select

from app.core.config import get_settings
from app.services.errors import DomainError

log = logging.getLogger(__name__)


class CompanyBotRunner:
    def __init__(self, company_id: int, token: str):
        self.company_id = company_id
        self.token = token
        self.bot = Bot(token=token)
        self.dp = Dispatcher(storage=MemoryStorage())
        self.username: str | None = None
        self._task: asyncio.Task | None = None

    async def start(self) -> str:
        """Validate the token and begin polling. Returns the bot username."""
        from app.services.telegram.handlers import build_router

        me = await self.bot.get_me()
        self.username = me.username
        self.dp.include_router(build_router(self.company_id))
        await self.bot.delete_webhook(drop_pending_updates=False)
        with suppress(Exception):
            from aiogram.types import BotCommand

            await self.bot.set_my_commands(
                [
                    BotCommand(command="start", description="Ro'yxatdan o'tish"),
                    BotCommand(command="navbat", description="Mening navbatim (QR-kod)"),
                    BotCommand(command="holat", description="Navbat holati"),
                ]
            )
        self._task = asyncio.create_task(
            self.dp.start_polling(self.bot, handle_signals=False),
            name=f"tg-bot-company-{self.company_id}",
        )
        log.info("Telegram bot @%s started for company %s", me.username, self.company_id)
        return me.username

    async def stop(self) -> None:
        with suppress(RuntimeError):
            await self.dp.stop_polling()
        if self._task is not None:
            self._task.cancel()
            with suppress(asyncio.CancelledError, Exception):
                await self._task
        await self.bot.session.close()
        log.info("Telegram bot stopped for company %s", self.company_id)


class BotManager:
    def __init__(self) -> None:
        self._runners: dict[int, CompanyBotRunner] = {}

    @property
    def enabled(self) -> bool:
        return get_settings().telegram_enabled

    def is_running(self, company_id: int) -> bool:
        return company_id in self._runners

    async def start_all(self) -> None:
        """Start bots for every company with a saved token (app startup)."""
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
        runner = CompanyBotRunner(company_id, token)
        try:
            username = await runner.start()
        except Exception:
            await runner.bot.session.close()
            raise
        self._runners[company_id] = runner
        return username

    async def set_token(self, company_id: int, token: str | None) -> str | None:
        """Apply a token change: restart the runner (or stop it when cleared).

        Returns the bot username, or None when the bot could not be started
        (disabled, cleared, or a network problem — the token is still saved).
        Raises DomainError for a token Telegram rejects as invalid.
        """
        existing = self._runners.pop(company_id, None)
        if existing is not None:
            await existing.stop()
        if not token or not self.enabled:
            return None
        try:
            return await self._start_runner(company_id, token)
        except TelegramUnauthorizedError:
            raise DomainError("Telegram bot tokeni yaroqsiz — BotFather'dan tekshiring") from None
        except TelegramNetworkError as exc:
            log.warning("Telegram unreachable while starting bot for company %s: %s", company_id, exc)
            return None

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

    async def send_photo(self, company_id: int, chat_id: int, photo, caption: str) -> None:
        runner = self._runners.get(company_id)
        if runner is None:
            return
        try:
            await runner.bot.send_photo(chat_id, photo=photo, caption=caption)
        except Exception as exc:
            log.warning("Failed to send photo to chat %s (company %s): %s", chat_id, company_id, exc)

    async def stop_all(self) -> None:
        runners = list(self._runners.values())
        self._runners.clear()
        for runner in runners:
            with suppress(Exception):
                await runner.stop()


bot_manager = BotManager()
