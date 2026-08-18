from collections.abc import AsyncIterator

from sqlalchemy import event, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.config import get_settings

settings = get_settings()

if settings.database_url.startswith("sqlite"):
    engine = create_async_engine(settings.database_url, echo=False)

    @event.listens_for(engine.sync_engine, "connect")
    def _sqlite_pragmas(dbapi_connection, _record):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.execute("PRAGMA busy_timeout=5000")
        cursor.close()

else:
    # PostgreSQL: a real pool sized for burst traffic. Total connections =
    # workers × (pool_size + max_overflow); keep it under the server's limit.
    engine = create_async_engine(
        settings.database_url,
        echo=False,
        pool_size=settings.db_pool_size,
        max_overflow=settings.db_max_overflow,
        pool_pre_ping=True,
        pool_recycle=1800,
    )


SessionFactory = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)


async def get_db() -> AsyncIterator[AsyncSession]:
    async with SessionFactory() as session:
        yield session


async def create_schema() -> None:
    """Create tables on startup. Under Postgres with several uvicorn workers
    this races, so it is serialized with an advisory lock. (For evolving
    production schemas, switch to Alembic migrations.)"""
    from app.db.base import Base
    import app.models  # noqa: F401 — register every model on Base.metadata

    async with engine.begin() as conn:
        if engine.dialect.name == "postgresql":
            await conn.execute(text("SELECT pg_advisory_xact_lock(752130421)"))
        await conn.run_sync(Base.metadata.create_all)
        # create_all never alters existing tables — add columns introduced
        # after a database was first created (poor man's forward migration)
        if engine.dialect.name == "postgresql":
            await conn.execute(
                text(
                    "ALTER TABLE sale_events ADD COLUMN IF NOT EXISTS branch_id INTEGER "
                    "REFERENCES branches (id) ON DELETE SET NULL"
                )
            )
        else:
            columns = (await conn.execute(text("PRAGMA table_info(sale_events)"))).all()
            if all(column[1] != "branch_id" for column in columns):
                await conn.execute(
                    text(
                        "ALTER TABLE sale_events ADD COLUMN branch_id INTEGER "
                        "REFERENCES branches (id) ON DELETE SET NULL"
                    )
                )
