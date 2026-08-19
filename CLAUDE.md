# SmartNavbat — CLAUDE.md

SmartNavbat (smartnavbat.uz) is a multi-tenant queue-management SaaS for sale
days: clients register via a company's Telegram bot and get a random 4-letter
uppercase code + QR; on the sale day they check in until a deadline; then the
queue runs ordered by **bot registration time among checked-in tickets only**.

## MANDATORY git workflow — `dev` is where you work, `main` is production

This repo has exactly two long-lived branches:

- **`main` — production.** Only ever receives merges from `dev`, and only
  code that is verified working. Never commit to `main` directly.
- **`dev` — development.** All work happens here: features, fixes,
  experiments.

For EVERY change, without exception:

1. `git checkout dev` (create it from `main` if it is missing) and commit
   the work there. If you are asked to work on some other branch, treat that
   branch as a stand-in for `dev` and still finish through step 2.
2. When the work is done, run the full verification below. **Only if
   everything passes** — backend tests green, frontend `tsc -b` and
   `vite build` clean — merge `dev` into `main` and push both branches.
   A red test or a broken build means `main` does not get the merge; fix it
   on `dev` first.
3. Never push work-in-progress, broken, or unverified code to `main`. Only
   working files reach production.

## MANDATORY workflow — read the rules before you code

Before implementing ANY request in this repo:

1. Read the rules that apply to what you are about to touch:
   - Backend work → `backend/CLAUDE.md`
   - Frontend work → `frontend/CLAUDE.md`
   - Anything touching auth, input, uploads, tokens, secrets, webhooks,
     rate limits, or new endpoints → `docs/rules/security.md`
2. After writing code and BEFORE declaring it done, self-review against
   `docs/rules/code-review.md` and run the verification commands below.
3. If a change conflicts with a rule, follow the rule or explain in the
   final summary why the exception is justified.

## Project map

```
backend/   FastAPI + SQLAlchemy 2.0 async + aiogram 3 (Python 3.11+)
  app/main.py       API service (embedded bots in single-process dev mode)
  app/bot_main.py   Bot service — the ONLY process talking to Telegram
  app/services/     queue logic, ticket numbers, QR (process pool),
                    debounced broadcasts, notify routing, bot manager
frontend/  React 18 + TypeScript + Vite SPA (TanStack Query, react-router)
docs/rules/         code-review + security rule sets (read them!)
docker-compose.yml  postgres + redis + api ×N + bot + nginx
```

## Verification commands (run before finishing)

```bash
cd backend && python3 -m pytest tests/ -q          # must be all green
cd frontend && npx tsc -b && npx vite build        # must be clean
# optional: re-run backend suite on Postgres:
# TEST_DATABASE_URL=postgresql+asyncpg://... python3 -m pytest tests/ -q
```

Then, and only when all of it passes, ship `dev` to production:

```bash
git checkout main && git merge --ff-only dev && git push origin main
git checkout dev  && git push origin dev
```

## Domain invariants (never break these)

- Queue order = `registered_at` (bot registration time) among CHECKED_IN
  tickets; late check-ins / skip-returns go to the end-of-day group
  (`queue_order = LATE_ORDER_BASE + event.late_seq`). Ticket "numbers" are
  random 4-letter uppercase codes, unique per event — never sequential,
  never reused.
- Calling is blocked until `event.checkin_until` passes.
- A second no-show cancels the ticket; the first sends it to end-of-day once.
- Tenancy: every staff query is scoped by `company_id`; cross-tenant access
  returns 404 (never 403 — don't leak existence).
- Two runtime modes, keep both working: no `REDIS_URL` → single process,
  embedded bots, in-memory WS; `REDIS_URL` set → API ×N workers + separate
  bot service, everything cross-process goes through Redis.

## Branding

- Product name: **SmartNavbat** (one word, capital S and N). Domain:
  **smartnavbat.uz**. UI language: Uzbek (latin). Code, comments, commits:
  English. Never hardcode another brand name.

## Conventions

- Timestamps are timezone-aware UTC everywhere; format for humans with
  `queue_service.fmt_local` (Asia/Tashkent). User-facing errors are Uzbek;
  logs are English.
- Never run CPU-bound work (bcrypt, PIL/QR) on the event loop — use the
  existing async wrappers.
- After any queue mutation call `schedule_event_broadcast(event_id)` —
  never rebuild/broadcast state inline.
