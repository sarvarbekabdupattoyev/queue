"""SmartNavbat API service.

Single-process dev (no REDIS_URL): also embeds the Telegram bots and keeps WS
rooms in memory — run exactly one worker.

Production (REDIS_URL set): run ``uvicorn app.main:app --workers N``. Bots
live in the separate bot service (``app.bot_main``); WS broadcasts fan out
through Redis pub/sub so any worker reaches every connected screen.
"""

import asyncio
import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from app.core.config import get_settings
from app.core.redis import close_redis
from app.db.session import create_schema, engine
from app.services import broadcast
from app.services.errors import DomainError
from app.services.qr_service import shutdown_qr_pool
from app.services.telegram.manager import bot_manager
from app.ws.manager import ws_manager

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s"
)
log = logging.getLogger("navbat")


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    if settings.database_url.startswith("sqlite"):
        Path(settings.database_url.split("///")[-1]).parent.mkdir(parents=True, exist_ok=True)
    await create_schema()
    settings.upload_dir.mkdir(parents=True, exist_ok=True)

    subscriber: asyncio.Task | None = None
    if settings.multi_process:
        # bots run in the dedicated bot service; this worker only relays WS
        subscriber = asyncio.create_task(ws_manager.run_subscriber(), name="ws-sub")
        log.info("SmartNavbat API worker started (multi-process mode)")
    else:
        await bot_manager.start_all()
        log.info("SmartNavbat API started (single-process mode, embedded bots)")

    yield

    if subscriber is not None:
        subscriber.cancel()
        try:
            await subscriber
        except (asyncio.CancelledError, Exception):
            pass
    await broadcast.shutdown()
    if not settings.multi_process:
        await bot_manager.stop_all()
    shutdown_qr_pool()
    await close_redis()
    await engine.dispose()


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title="SmartNavbat API",
        version="1.0.0",
        lifespan=lifespan,
        docs_url="/api/docs",
        openapi_url="/api/openapi.json",
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.exception_handler(DomainError)
    async def domain_error_handler(_request: Request, exc: DomainError) -> JSONResponse:
        return JSONResponse(status_code=exc.status_code, content={"detail": exc.message})

    from app.api.routes import auth, company, desks, employees, events, public, queue, ws

    for router in (
        auth.router,
        company.router,
        employees.router,
        desks.router,
        events.router,
        queue.router,
        public.router,
        ws.router,
    ):
        app.include_router(router, prefix="/api")

    settings.upload_dir.mkdir(parents=True, exist_ok=True)
    app.mount("/media", StaticFiles(directory=settings.upload_dir), name="media")

    @app.get("/api/health")
    async def health() -> dict:
        return {"status": "ok"}

    return app


app = create_app()
