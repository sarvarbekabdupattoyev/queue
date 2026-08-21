import logging
from collections.abc import AsyncIterator

from sqlalchemy import event, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.config import get_settings

log = logging.getLogger(__name__)

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
        await _add_missing_indexes(conn)
        await _drop_stale_constraints(conn)
        await _migrate_single_branch_events(conn)
        await _migrate_company_bot_tokens(conn)
        await _migrate_call_timeout_minutes(conn)


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


# Indexes added to tables that already existed in earlier deployments.
# create_all() only ever CREATEs missing tables, so an index added to a table
# that is already there never reaches an upgraded database on its own.
_ADDED_INDEXES: tuple[str, ...] = (
    "CREATE INDEX IF NOT EXISTS ix_ticket_waiting "
    "ON tickets (event_id, status, queue_order, id)",
    "CREATE INDEX IF NOT EXISTS ix_ticket_waiting_branch "
    "ON tickets (event_id, branch_id, status, queue_order, id)",
)

# Superseded by the covering waiting-list indexes above — their columns are a
# leading prefix of the new ones, and every redundant index costs write
# throughput during a registration burst.
_DROPPED_INDEXES: tuple[str, ...] = (
    "ix_ticket_event_status",
    "ix_ticket_event_branch_status",
)

_ACTIVE_DESK_PREDICATE = "desk_id IS NOT NULL AND status IN ('CALLED', 'SERVING')"


async def _add_missing_indexes(conn) -> None:
    for statement in _ADDED_INDEXES:
        await conn.execute(text(statement))
    await _add_active_desk_index(conn)
    for name in _DROPPED_INDEXES:
        await conn.execute(text(f"DROP INDEX IF EXISTS {name}"))


async def _add_active_desk_index(conn) -> None:
    """A desk serves one client at a time; that is enforced by a partial
    unique index (see Ticket). A database upgraded from before it may already
    hold a desk with two active tickets — precisely the bug the index
    prevents — and creating it would then fail and take startup down with it.
    Check first and leave the data for an operator to sort out instead."""
    clash = await conn.scalar(
        text(
            "SELECT desk_id FROM tickets "
            f"WHERE {_ACTIVE_DESK_PREDICATE} "
            "GROUP BY desk_id HAVING COUNT(*) > 1 LIMIT 1"
        )
    )
    if clash is not None:
        log.warning(
            "Desk %s holds more than one active ticket — skipping the "
            "uq_ticket_desk_active index; finish or skip the duplicates and "
            "restart to enforce one client per desk",
            clash,
        )
        return
    await conn.execute(
        text(
            "CREATE UNIQUE INDEX IF NOT EXISTS uq_ticket_desk_active "
            f"ON tickets (desk_id) WHERE {_ACTIVE_DESK_PREDICATE}"
        )
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
    # Only seed events that have NO links yet. Matching on the exact pair
    # would resurrect a branch the owner has since removed from the event,
    # every single startup.
    await conn.execute(
        text(
            "INSERT INTO event_branches (event_id, branch_id) "
            "SELECT e.id, e.branch_id FROM sale_events e "
            "WHERE e.branch_id IS NOT NULL AND NOT EXISTS ("
            "  SELECT 1 FROM event_branches eb WHERE eb.event_id = e.id)"
        )
    )


async def _migrate_company_bot_tokens(conn) -> None:
    """Earlier releases kept ONE bot per company in companies.telegram_bot_token;
    a company now runs up to three through company_bots. Without this, every
    deployed tenant's bot would silently stop after the upgrade."""
    if engine.dialect.name == "postgresql":
        has_column = await conn.scalar(
            text(
                "SELECT 1 FROM information_schema.columns "
                "WHERE table_name = 'companies' AND column_name = 'telegram_bot_token'"
            )
        )
    else:
        columns = (await conn.execute(text("PRAGMA table_info(companies)"))).all()
        has_column = any(row[1] == "telegram_bot_token" for row in columns)
    if not has_column:
        return
    await conn.execute(
        text(
            "INSERT INTO company_bots (company_id, token, username, created_at) "
            "SELECT c.id, c.telegram_bot_token, c.telegram_bot_username, "
            "       CURRENT_TIMESTAMP "
            "FROM companies c "
            "WHERE c.telegram_bot_token IS NOT NULL AND c.telegram_bot_token <> '' "
            "  AND NOT EXISTS (SELECT 1 FROM company_bots b WHERE b.company_id = c.id) "
            "  AND NOT EXISTS (SELECT 1 FROM company_bots b WHERE b.token = c.telegram_bot_token)"
        )
    )


async def _migrate_call_timeout_minutes(conn) -> None:
    """call_timeout_minutes used to be one global CALL_TIMEOUT_MINUTES env
    value shared by every company; each company now owns its own (Settings).
    A brand-new column would otherwise silently reset every existing
    company to the schema default (10) the moment this ships -- companies
    already relying on the env value (whatever it happened to be on this
    deployment) get that exact value carried over instead, once, here. Never
    runs again once the column exists, so it can never clobber an owner's
    later customization."""
    if engine.dialect.name == "postgresql":
        has_column = await conn.scalar(
            text(
                "SELECT 1 FROM information_schema.columns "
                "WHERE table_name = 'companies' AND column_name = 'call_timeout_minutes'"
            )
        )
    else:
        columns = (await conn.execute(text("PRAGMA table_info(companies)"))).all()
        has_column = any(row[1] == "call_timeout_minutes" for row in columns)
    if has_column:
        return
    await conn.execute(
        text("ALTER TABLE companies ADD COLUMN call_timeout_minutes INTEGER NOT NULL DEFAULT 10")
    )
    await conn.execute(
        text("UPDATE companies SET call_timeout_minutes = :v"),
        {"v": get_settings().call_timeout_minutes},
    )


# Constraints from earlier releases that the new schema replaces. create_all()
# never touches an existing table, so an upgraded database keeps enforcing them.
_DROPPED_CONSTRAINTS: tuple[tuple[str, str], ...] = (
    # desk numbers used to be unique per company; they are now unique per
    # (company, branch) so each branch can have its own "1-stol"
    ("desks", "uq_desk_company_number"),
)


async def _drop_stale_constraints(conn) -> None:
    if engine.dialect.name != "postgresql":
        # SQLite cannot drop a constraint; dev databases are recreated instead
        return
    for table, constraint in _DROPPED_CONSTRAINTS:
        await conn.execute(
            text(f"ALTER TABLE {table} DROP CONSTRAINT IF EXISTS {constraint}")
        )
