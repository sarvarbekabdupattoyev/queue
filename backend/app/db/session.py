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
        await _add_missing_columns(conn)
        await _migrate_single_branch_events(conn)


# Columns added to tables that already existed in earlier deployments.
# create_all() only ever CREATEs, so it never adds them on its own.
_ADDED_COLUMNS: tuple[tuple[str, str, str], ...] = (
    ("tickets", "branch_id", "INTEGER REFERENCES branches (id) ON DELETE SET NULL"),
    ("tickets", "bot_id", "INTEGER REFERENCES company_bots (id) ON DELETE SET NULL"),
    ("users", "branch_id", "INTEGER REFERENCES branches (id) ON DELETE SET NULL"),
    ("desks", "branch_id", "INTEGER REFERENCES branches (id) ON DELETE CASCADE"),
)


async def _add_missing_columns(conn) -> None:
    """Poor man's forward migration for databases created before these
    columns existed (production evolution still wants Alembic)."""
    for table, column, definition in _ADDED_COLUMNS:
        if engine.dialect.name == "postgresql":
            await conn.execute(
                text(f"ALTER TABLE {table} ADD COLUMN IF NOT EXISTS {column} {definition}")
            )
        else:
            existing = (await conn.execute(text(f"PRAGMA table_info({table})"))).all()
            if all(row[1] != column for row in existing):
                await conn.execute(
                    text(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")
                )


async def _migrate_single_branch_events(conn) -> None:
    """Earlier releases pinned an event to ONE branch via sale_events.branch_id;
    events now run in MANY branches through the event_branches table. Copy any
    surviving single-branch links over so deployed data keeps its branch."""
    if engine.dialect.name == "postgresql":
        has_column = await conn.scalar(
            text(
                "SELECT 1 FROM information_schema.columns "
                "WHERE table_name = 'sale_events' AND column_name = 'branch_id'"
            )
        )
    else:
        columns = (await conn.execute(text("PRAGMA table_info(sale_events)"))).all()
        has_column = any(row[1] == "branch_id" for row in columns)
    if not has_column:
        return
    await conn.execute(
        text(
            "INSERT INTO event_branches (event_id, branch_id) "
            "SELECT e.id, e.branch_id FROM sale_events e "
            "WHERE e.branch_id IS NOT NULL AND NOT EXISTS ("
            "  SELECT 1 FROM event_branches eb "
            "  WHERE eb.event_id = e.id AND eb.branch_id = e.branch_id)"
        )
    )
