# NAVBAT — Queue Management System

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

## Repository layout

```
backend/            FastAPI app
  app/core/         settings, JWT, password hashing, phone normalization
  app/models/       SQLAlchemy 2.0 models (User, Company, Desk, SaleEvent, Ticket)
  app/services/     queue logic, ticket numbers, QR, Telegram bot manager + handlers
  app/api/routes/   auth, company, employees, desks, events, queue, public, ws
  tests/            pytest suite for the queue rules
frontend/           React 18 + Vite + TypeScript SPA (TanStack Query, react-router)
docker-compose.yml  production-style: uvicorn + nginx (static SPA + API/WS proxy)
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

## Quick start (Docker)

```bash
echo "SECRET_KEY=$(openssl rand -hex 32)" > .env
docker compose up --build     # app on http://localhost:80
```

SQLite data and uploaded logos live in named volumes. For PostgreSQL set
`DATABASE_URL=postgresql+asyncpg://user:pass@host/db` for the backend and install the
`postgres` extra in `backend/Dockerfile` (`pip install .[postgres]`).

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

- Passwords hashed with bcrypt; JWT (HS256) access tokens; role checks on every route.
- Staff endpoints are scoped to the caller's company — cross-tenant access returns 404.
- The public display exposes numbers only (no names/phones); ticket pages are addressable
  only by the unguessable QR code; display links use random codes.
- Set a strong `SECRET_KEY` and serve over HTTPS in production (camera scanning requires it).
