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


async def send_telegram_text(company_id: int, chat_id: int, text: str) -> None:
    redis = get_redis()
    if redis is not None:
        try:
            await redis.publish(
                CH_NOTIFY,
                json.dumps({"company_id": company_id, "chat_id": chat_id, "text": text}),
            )
        except Exception as exc:
            log.warning("Failed to publish Telegram notification: %s", exc)
        return

    from app.services.telegram.manager import bot_manager

    # fire-and-forget: bot_manager.send_text logs failures itself
    asyncio.get_running_loop().create_task(
        bot_manager.send_text(company_id, chat_id, text)
    )


async def notify_bot_token_changed(company_id: int) -> None:
    """Tell the bot service to reload one company's bot (multi-process only)."""
    redis = get_redis()
    if redis is None:
        return
    try:
        await redis.publish(CH_BOT_CONTROL, json.dumps({"company_id": company_id}))
    except Exception as exc:
        log.warning("Failed to publish bot-control message: %s", exc)
