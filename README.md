# SmartNavbat — smartnavbat.uz

Multi-tenant online queue platform for sale days ("sotuv kuni"): clients register through a
company's **Telegram bot** and receive a **random 4-digit number + QR code**; on the sale day they
check in at the reception (QR scan or manual number entry) until a deadline set by the company;
when the deadline passes the queue starts — ordered by **bot registration time**, counting **only
checked-in tickets**. Managers call clients to their desks, a TV board shows live numbers, and the
bot notifies clients at every step.

Built with **FastAPI** (Python) + **React** (TypeScript). UI and bot speak Uzbek.

```
Client (Telegram)              Reception (scanner role)        Office TV (public link)     Manager (desk)
/start → name, phone           QR scanned / number typed  →    №4821 — desk 3              "Call next"
→ №4821 + QR code              "checked in" until deadline     next: 7203 1544 …           Arrived / No-show / Done
```

## The core rule

1. The owner creates a **sale event** with two times: `starts_at` (sale day begins) and
   `checkin_until` (QR scanning deadline — **the client company sets this**).
2. The Telegram bot registers clients any time before `checkin_until` and hands out **random,
   non-sequential 4-digit numbers** (1000–9999, unique per event).
3. Until `checkin_until`, reception scans QR codes (or types the number). Calling is blocked.
4. At `checkin_until` the queue starts. Order = **registration time in the bot**, among
   **scanned tickets only**. The number itself and the arrival order don't matter.
5. Late arrivals (scanned after the deadline) and skipped clients who return join the
   **end-of-day group** (once; a second no-show cancels the ticket).

## Features

- **Owner accounts** — phone + password sign-up, one company per owner.
- **Company profile** — name, logo, contact phone numbers, office locations, Telegram bot token.
- **Employees** — created by the owner with a **server-generated password** (shown once),
  roles: `manager` (desk panel) and `scanner` (reception check-in).
- **Desks ("tables")** — numbered desks, optionally pinned to a manager.
- **Sale events** — many per company, each with its own dates, live phase
  (`registration → checkin → queue`) and an unguessable public display link.
- **Per-company Telegram bots** (aiogram): registration conversation (name → surname → phone via
  contact button), QR photo delivery, `/navbat` and `/holat` commands, push notifications on
  check-in / call / skip / finish.
- **Live everywhere** — WebSocket state for the TV display, manager panel, scanner and event
  dashboard, with automatic reconnect + HTTP polling fallback.
- **TV display** — called numbers with desk and countdown ring, next-up list, stats, a
  "queue starts in …" countdown before the deadline, chime + fullscreen.
- **Scanner page** — USB scanner / manual entry (auto-focused input) and in-browser camera QR
  scanning (jsQR); big color-coded result states, on-time vs end-of-day feedback.
- **Manager panel** — call next / arrived / no-show / re-call / finish, call timer, other desks,
  live waiting list.
- **Client ticket page** — `/t/{code}` public status page with QR, position and desk.

## Architecture

Built for registration bursts of 1000–2000 bot requests in a few seconds:

```
                nginx (TLS, WS upgrade, SPA, rate limits)
                       │
       ┌───────────────┼───────────────────┐
       │               │                   │
  API workers ×N   Bot service         static SPA
  (uvicorn)        (webhook or polling,
       │            exactly 1 replica)
       └──────┬────────┴──── Redis (FSM state · WS pub/sub · notifications)
              │
         PostgreSQL (asyncpg, pooled)
```

Key decisions:

- **PostgreSQL in production** — SQLite stays a dev-only default (single
  writer); the compose stack runs Postgres with a sized asyncpg pool.
- **The bot is its own service** (`app.bot_main`) — the only process talking
  to Telegram, so N API workers never fight over polling (no 409s). Webhook
  mode ACKs Telegram instantly and processes updates in semaphore-bounded
  tasks; long polling remains the zero-config fallback.
- **Redis pub/sub for WebSockets** — every API worker relays broadcasts to
  the sockets it holds, so `--workers N` reaches every screen.
- **RedisStorage for the bot FSM** — half-finished registrations survive
  restarts; keys are bot-scoped so tenants never collide.
- **Debounced state broadcasts** — a burst marks an event dirty thousands of
  times, screens get at most one rebuilt state per 200 ms window
  (measured: 2000 registrations → ~36 pushes instead of 4000).
- **CPU off the event loop** — QR rendering (pure-Python matrix build, GIL)
  runs in a small process pool; bcrypt runs in threads.
- Measured on 4 shared cores: **2000 registrations in ~9 s end-to-end**
  (DB path alone: 364 reg/s) — well above Telegram's own ~30 msg/s per-bot
  delivery cap, which is the real-world ceiling for sending 2000 QR photos.

## Repository layout

```
backend/            FastAPI app
  app/core/         settings, JWT, password hashing, phones, Redis client
  app/models/       SQLAlchemy 2.0 models (User, Company, Desk, SaleEvent, Ticket)
  app/services/     queue logic, ticket numbers, QR (process pool), debounced
                    broadcasts, notify routing, Telegram bot manager + handlers
  app/api/routes/   auth, company, employees, desks, events, queue, public, ws
  app/main.py       API service (embedded bots in single-process dev mode)
  app/bot_main.py   bot service (webhook receiver / poller, notify consumer)
  tests/            pytest suite (queue rules + burst machinery; runs on
                    SQLite by default, TEST_DATABASE_URL=postgres re-runs it on PG)
frontend/           React 18 + Vite + TypeScript SPA (TanStack Query, react-router)
docker-compose.yml  postgres + redis + api ×N workers + bot service + nginx
```

## Quick start (development)

Backend (Python 3.11+):

```bash
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
cp .env.example .env          # set SECRET_KEY
uvicorn app.main:app --reload # http://localhost:8000  (docs: /api/docs)
```

Frontend (Node 20+):

```bash
cd frontend
npm install
npm run dev                   # http://localhost:5173 (proxies /api to :8000)
```

Tests:

```bash
cd backend && pytest
```

## Quick start (Docker, production-style)

```bash
echo "SECRET_KEY=$(openssl rand -hex 32)" > .env
echo "POSTGRES_PASSWORD=$(openssl rand -hex 16)" >> .env
docker compose up --build     # app on http://localhost:80
```

Starts PostgreSQL, Redis, the API (`API_WORKERS`, default 4), the bot
service, and nginx. Postgres data, Redis AOF, and uploaded logos live in
named volumes.

**Telegram webhook mode (recommended for sale-day bursts):** put the stack
behind HTTPS, set `BOT_WEBHOOK_BASE=https://smartnavbat.uz/tgwh` in `.env` and
restart the bot service. Each company bot is registered at
`{base}/{company_id}` with a per-company HMAC secret; without a public URL
the bot service falls back to long polling automatically.

## Using the system

1. **Sign up** at `/register`, create your company.
2. **Settings** → add contact phones, locations, upload the logo, and paste the bot token from
   **@BotFather** (`/newbot`). The token is validated via `getMe` and the bot starts polling
   immediately — no restart needed.
3. **Employees** → add managers and scanners; hand each the one-time generated password
   (login = phone number).
4. **Desks** → create numbered desks, optionally assign managers.
5. **Events** → create the sale day with its start and the **scanning deadline**.
6. Clients write `/start` to your bot → get their number + QR.
7. On the day: scanners open `/scanner`, managers `/manager`, the TV opens the public
   display link from the event page. Everything updates live.

## API overview

| Method | Path | Who | Purpose |
|---|---|---|---|
| POST | `/api/auth/register` · `/login` | public | owner sign-up, any-user login |
| GET | `/api/auth/me` | any | current user |
| POST/GET/PATCH | `/api/company` (+ `/logo`, `/phones`, `/locations`) | owner | company profile, bot token |
| CRUD | `/api/employees` (+ `/reset-password`) | owner | staff with generated passwords |
| CRUD | `/api/desks` | owner (read: staff) | manager desks |
| CRUD | `/api/events` (+ `/state`, `/tickets`, `/seed`) | owner (read: staff) | sale events |
| POST | `/api/queue/{event}/checkin` | staff | QR code or 4-digit number |
| POST | `/api/queue/{event}/call` · `recall` · `serving` · `skip` · `done` · `cancel` | manager/owner | desk actions |
| GET | `/api/public/display/{code}` · `/api/public/tickets/{code}` | public | TV board, client ticket |
| WS | `/api/ws/display/{code}` · `/api/ws/staff/{event}?token=` | public / staff | live state push |

## Security notes

- Passwords hashed with bcrypt (off the event loop); JWT (HS256) access tokens; role checks
  on every route.
- Staff endpoints are scoped to the caller's company — cross-tenant access returns 404.
- The public display exposes numbers only (no names/phones); ticket pages are addressable
  only by the unguessable QR code; display links use random codes.
- Telegram webhooks are validated with a per-company HMAC secret
  (`X-Telegram-Bot-Api-Secret-Token`); nginx rate-limits the API (20 r/s per IP)
  and auth endpoints (5 r/s per IP).
- Set a strong `SECRET_KEY` and serve over HTTPS in production (camera scanning and
  Telegram webhooks require it).

## Scaling notes

- `API_WORKERS` scales reads/staff actions; DB connections = workers × (pool + overflow) —
  keep under Postgres `max_connections`.
- The bot service stays a **single replica** (Telegram allows one consumer per token).
  Inside it, updates are processed concurrently up to `BOT_MAX_CONCURRENT_UPDATES`.
- The hard external limit is Telegram itself: ~30 outgoing messages/second per bot.
  The system absorbs the incoming burst instantly (webhook ACK + queue in-process) and
  the QR photos drain at Telegram's permitted rate.
- Single-process dev mode (no `REDIS_URL`) keeps everything in one uvicorn process —
  never run that with `--workers > 1`.
