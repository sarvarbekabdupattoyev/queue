"""Outbound Telegram notifications from queue actions.

Single-process mode: hand the message to the embedded bot manager as a
background task (a Telegram API round-trip must not sit inside a staff
request). Multi-process mode: publish to Redis — the bot service is the only
process talking to Telegram, so N API workers never fight over polling.
"""

import asyncio
import json
import logging

from app.core.redis import CH_BOT_CONTROL, CH_NOTIFY, get_redis

log = logging.getLogger(__name__)

# asyncio holds only a weak reference to a running task, so a send that nobody
# awaits can be garbage-collected before it reaches Telegram. Keeping the task
# here until it finishes is what makes "fire-and-forget" actually deliver.
_pending: set[asyncio.Task] = set()


async def send_telegram_text(
    company_id: int, chat_id: int, text: str, bot_id: int | None = None
) -> None:
    """``bot_id`` is the CompanyBot the client registered through — messages
    go out via that bot when it is running (other bots of the company may not
    be allowed to message the client)."""
    redis = get_redis()
    if redis is not None:
        try:
            await redis.publish(
                CH_NOTIFY,
                json.dumps(
                    {
                        "company_id": company_id,
                        "chat_id": chat_id,
                        "text": text,
                        "bot_id": bot_id,
                    }
                ),
            )
        except Exception as exc:
            log.warning("Failed to publish Telegram notification: %s", exc)
        return

    from app.services.telegram.manager import bot_manager

    # fire-and-forget: bot_manager.send_text logs failures itself
    task = asyncio.get_running_loop().create_task(
        bot_manager.send_text(company_id, chat_id, text, bot_id)
    )
    _pending.add(task)
    task.add_done_callback(_pending.discard)


async def notify_bot_token_changed(company_id: int) -> None:
    """Tell the bot service to reload one company's bots (multi-process only)."""
    redis = get_redis()
    if redis is None:
        return
    try:
        await redis.publish(CH_BOT_CONTROL, json.dumps({"company_id": company_id}))
    except Exception as exc:
        log.warning("Failed to publish bot-control message: %s", exc)
