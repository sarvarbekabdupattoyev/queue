# Backend rules — SmartNavbat (read before touching backend/)

Senior-level practices for this FastAPI + SQLAlchemy 2.0 (async) + aiogram 3
codebase. The root `CLAUDE.md` invariants apply on top of these.

## Architecture rules

- **Two processes, one codebase.** `app/main.py` = API (may run `--workers N`
  when Redis is set), `app/bot_main.py` = bot service (exactly one replica).
  Never start polling/bots in the API when `settings.multi_process` is true.
  Anything that must cross processes (WS broadcast, Telegram notify, token
  reload) goes through the Redis channels in `app/core/redis.py`.
- **Services own business logic; routes stay thin.** A route parses/authorizes,
  calls one service function, shapes the response. Queue rules live only in
  `app/services/queue_service.py` — never duplicate them in routes or bot
  handlers.
- **Side effects off the request path.** State pushes: only
  `schedule_event_broadcast(event_id)` (debounced, own session). Telegram
  sends: only `app/services/notify.py`. Never await a Telegram API call inside
  an HTTP request handler.
- **CPU never blocks the loop.** bcrypt → `hash_password_async` /
  `verify_password_async`; QR → `qr_png_bytes_async` / `qr_data_url_async`
  (process pool). New CPU-heavy code follows the same pattern; new blocking
  I/O gets `asyncio.to_thread`.

## Database rules

- SQLAlchemy 2.0 style only (`Mapped[...]`, `select()`); no legacy Query API.
- Timezone-aware UTC datetimes via the `UTCDateTime` type; never store naive.
- Every new hot-path filter gets an index; uniqueness is enforced by DB
  constraints, not just application checks — handle `IntegrityError` with
  rollback + retry (see `ticket_service.create_ticket`).
- After `rollback()`, ORM attributes are expired: never dereference held ORM
  objects afterwards — capture plain ids/values up front or re-`get()` them.
- Sessions: request-scoped via `DbSession` dependency in routes; background
  tasks and bot handlers open their own `SessionFactory()` — never share a
  session across tasks.
- Multi-tenancy: every query on company-owned rows filters by the caller's
  `company_id` (use `OwnCompany` / `CompanyEvent` deps). Missing OR foreign →
  404.
- Schema changes: update models + note in the PR that fresh deploys pick it
  up via `create_schema()`; production evolution needs Alembic (say so).

## API rules

- Pydantic v2 schemas for every request/response; validators normalize input
  (phones via `normalize_phone`). No raw `dict` request bodies.
- AuthZ is declarative: `require_roles(...)` dependencies, not inline ifs.
- Errors: raise `DomainError`/`ConflictError`/`NotFoundError` in services,
  `HTTPException` in routes; user-facing messages in Uzbek. Never leak stack
  traces, SQL, or internal ids in error text.
- New endpoints: add to README's API table + a test.

## Telegram bot rules

- Handlers are module-level functions in `handlers.py`; `company_id` comes as
  an injected argument (dispatcher workflow data) — never closures per
  company, never global mutable state.
- Everything Telegram-outbound goes through `BotManager`; it must survive one
  broken token without affecting other tenants (log + continue).
- Webhook route must stay fast: validate secret (constant-time), enqueue,
  return — processing happens in semaphore-bounded tasks.
- FSM state must work on both MemoryStorage and RedisStorage — don't put
  non-JSON-serializable values into FSM data.

## Testing rules

- Every behavior change lands with a pytest test; queue-rule changes get an
  ordering/permission test. Tests must pass on SQLite AND PostgreSQL
  (`TEST_DATABASE_URL`).
- Tests never talk to real Telegram or the network; `TELEGRAM_ENABLED=0`.
- Time-dependent logic is tested by constructing datetimes, never `sleep`.

## Style

- Type hints everywhere; `from __future__` not needed (3.11+). Match the
  existing import order (stdlib / third-party / app). Log in English with
  context ids (`company %s`, `event %s`); no `print`.
