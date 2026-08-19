"""SmartNavbat bot service — the single process that talks to Telegram.

Run with:  uvicorn app.bot_main:app --port 8081

Requires REDIS_URL: API workers publish notifications and token changes to
Redis and this service consumes them; running it without Redis alongside an
embedded-mode API would double-poll every bot (Telegram 409s).

In webhook mode (BOT_WEBHOOK_BASE set) Telegram POSTs updates to
``/tgwh/{bot_id}``; the route ACKs immediately and processing happens in
semaphore-bounded tasks, which is what absorbs 1000–2000 registrations in a
few seconds. Without a public URL it falls back to long polling.
"""

import asyncio
import logging
from contextlib import asynccontextmanager, suppress

from fastapi import FastAPI, Header, HTTPException, Request
from fastapi.responses import JSONResponse

from app.core.config import get_settings
from app.core.redis import close_redis
from app.db.session import create_schema, engine
from app.services import broadcast
from app.services.qr_service import qr_png_bytes_async, shutdown_qr_pool
from app.services.telegram.manager import bot_manager

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s"
)
log = logging.getLogger("navbat.bot")


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    if not settings.multi_process:
        raise RuntimeError(
            "The bot service needs REDIS_URL. Without Redis, run the API alone — "
            "it embeds the bots in single-process mode."
        )
    await create_schema()
    background: list[asyncio.Task] = []
    if settings.telegram_enabled:
        # spawn the QR worker processes before the first burst hits
        with suppress(Exception):
            await qr_png_bytes_async("warmup")
        await bot_manager.start_all()
        background = [
            asyncio.create_task(bot_manager.run_notify_subscriber(), name="tg-notify-sub"),
            asyncio.create_task(bot_manager.run_control_subscriber(), name="tg-control-sub"),
        ]
        log.info("Bot service started (%s mode)", "webhook" if settings.bot_webhook_base else "polling")
    else:
        log.warning("TELEGRAM_ENABLED=0 — bot service is idle")
    yield
    for task in background:
        task.cancel()
    for task in background:
        try:
            await task
        except (asyncio.CancelledError, Exception):
            pass
    await broadcast.shutdown()
    await bot_manager.stop_all()
    shutdown_qr_pool()
    await close_redis()
    await engine.dispose()


app = FastAPI(title="SmartNavbat Bot Service", lifespan=lifespan, docs_url=None, openapi_url=None)


@app.post("/tgwh/{bot_id}")
async def telegram_webhook(
    bot_id: int,
    request: Request,
    x_telegram_bot_api_secret_token: str = Header(default=""),
) -> dict:
    payload = await request.json()
    accepted = await bot_manager.feed_webhook(
        bot_id, x_telegram_bot_api_secret_token, payload
    )
    if not accepted:
        # unknown bot or wrong secret — don't leak which
        raise HTTPException(status_code=403, detail="forbidden")
    return {"ok": True}


@app.get("/healthz")
async def healthz() -> JSONResponse:
    """Container healthcheck: the service is healthy only while its database
    and Redis (both required in bot-service mode) answer."""
    from sqlalchemy import text

    from app.core.redis import get_redis
    from app.db.session import SessionFactory

    checks: dict[str, object] = {"bots": len(bot_manager._runners)}
    healthy = True
    try:
        async with SessionFactory() as db:
            await db.execute(text("SELECT 1"))
        checks["database"] = "ok"
    except Exception:
        log.exception("Health check: database unreachable")
        checks["database"] = "down"
        healthy = False
    redis = get_redis()
    if redis is not None:
        try:
            await redis.ping()
            checks["redis"] = "ok"
        except Exception:
            log.exception("Health check: redis unreachable")
            checks["redis"] = "down"
            healthy = False
    return JSONResponse(
        status_code=200 if healthy else 503,
        content={"status": "ok" if healthy else "degraded", **checks},
    )
