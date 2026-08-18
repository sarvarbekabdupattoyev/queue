import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from app.core.config import get_settings
from app.db.base import Base
from app.db.session import engine
from app.services.errors import DomainError
from app.services.telegram.manager import bot_manager

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s"
)
log = logging.getLogger("navbat")


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    db_path = settings.database_url.split("///")[-1]
    if settings.database_url.startswith("sqlite"):
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    settings.upload_dir.mkdir(parents=True, exist_ok=True)
    await bot_manager.start_all()
    log.info("NAVBAT backend started")
    yield
    await bot_manager.stop_all()
    await engine.dispose()


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title="NAVBAT API",
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
