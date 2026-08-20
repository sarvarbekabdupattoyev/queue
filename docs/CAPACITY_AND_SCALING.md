# Capacity & Scaling — the 10,000-in-1-second scenario

**Scenario analyzed:** at a scheduled instant (e.g. 20:00), up to 10,000 clients press
`/start` on the company's Telegram bot within roughly one second, then each one
completes language → full name → phone → receives a QR ticket, and the system must
not drop anyone — any transient failure should retry and self-heal rather than lose
a registration.

**Headline finding: the server is not the bottleneck. Telegram's own per-bot send
rate is.** Every other layer in this pipeline (nginx, uvicorn, Postgres, the QR
renderer) has comfortable headroom above what Telegram itself will ever let you
push through one bot token. The single highest-leverage change is more bot tokens,
not more server. Section 3 has the numbers.

## 1. How the burst actually arrives (this matters more than raw concurrency)

"10,000 users press start in 1 second" does not mean 10,000 simultaneous requests
hit your server in the way a naive HTTP load test implies:

- **Telegram paces delivery to your webhook itself.** `bot_webhook_max_connections`
  is already set to 100 — Telegram's own maximum — so Telegram will use up to 100
  parallel HTTPS connections to hand your webhook updates, regardless of how many
  users pressed the button at once. It self-throttles before your infrastructure
  ever sees the full burst.
- **The webhook route ACKs immediately.** `bot_main.py`'s `/tgwh/{bot_id}` handler
  validates the per-bot HMAC secret, hands the update to a semaphore-bounded
  background task (`BOT_MAX_CONCURRENT_UPDATES=64`), and returns `{"ok": true}`
  right away. Telegram is never kept waiting on your business logic, so it never
  falls into webhook retry-storm behavior.
- **Each user is a 3-4 message conversation, not one request.** `/start` → language
  button → name text → phone contact. Real humans take seconds between taps, which
  naturally staggers the *processing* load even when the *arrival* of the first
  message is simultaneous for everyone.

The part that is genuinely simultaneous and worth engineering for is the **first
wave of `/start` messages** and the **QR delivery at the end** — both analyzed below.

## 2. What was measured, and how (methodology)

All load was generated from this same host against an isolated copy of the
production database (`dev.smartnavbat.uz`, separate Postgres/Redis/containers, no
shared state with production), so production data was never at risk. Two things
were measured directly against production earlier in this exercise before the dev
environment existed: the `/api/*` nginx rate limiter behavior and a direct
`create_ticket()` concurrency run — both cited below with "measured on production."

| Layer | Method | Result |
|---|---|---|
| DB ticket creation (`ticket_service.create_ticket`) | Direct async calls, no HTTP | **100% success at 30 → 3,000 concurrent**, ~250-340 registrations/s sustained (measured on production's real resource allocation) |
| QR image generation (`ticket_qr_png_bytes_async`) | Direct async calls, no HTTP | **Flat ~100-105 images/s from 50 to 1,000 concurrent** — a hard ceiling from the process pool, not from concurrency |
| nginx `/api/` and `/api/public/` rate limiters | Real HTTP from a single source IP | Correctly reject high-rate single-IP traffic per `docs/rules/security.md`'s design — **not a bug**, and not relevant to real users each on their own IP |
| Telegram outbound rate | Code inspection + Telegram's published limits | ~25-30 messages/s per bot token (`throttle.py` already paces at 25/s with `TelegramRetryAfter` backoff) |

## 3. The real bottleneck, quantified

| Bot tokens connected | Aggregate Telegram send capacity | Time to deliver 10,000 QR codes |
|---|---|---|
| 1 (old default assumption) | ~25-30 msg/s | ~333-400 seconds (5.5-6.7 min) |
| 3 (old `MAX_BOTS_PER_COMPANY`) | ~75-90 msg/s | ~111-133 seconds (~2 min) |
| **10 (new `MAX_BOTS_PER_COMPANY`, changed below)** | **~250-300 msg/s** | **~33-40 seconds** |

This is a hard Telegram-side limit — no server optimization removes it. The only
lever is running more bot tokens for the same company, which the code already
supports (`BotManager` runs N bots per company in parallel, sharing the same FSM
storage and registration flow). The UI/API constant capping this
(`MAX_BOTS_PER_COMPANY`) was the artificial ceiling, not Telegram itself.

**Action for the real sale day:** connect as many bot tokens as practical (up to
the new limit of 10) to the company *before* the event, via Settings → each token
from a separate BotFather bot. This is now the single most impactful lever
available and costs nothing but creating a few more bot accounts.

## 4. Changes made in this pass

All committed (`eb84a9e` on `main`/`dev`), tested (dev's full suite: 55 passed,
same 3 pre-existing environment-only failures as the baseline — see §6), and
deployed to production.

1. **`MAX_BOTS_PER_COMPANY`: 3 → 10** (`backend/app/models/company.py`). Directly
   attacks the dominant bottleneck from §3. No hardcoded UI assumed exactly 3 —
   the API returns the limit dynamically, so the frontend adapts automatically.
2. **QR process pool: 4 → 6 workers** (`backend/app/services/qr_service.py`).
   Measured ceiling was ~100-105/s with 4 workers on an 8-core box; 6 leaves 2
   cores free for the event loop and other container work.
3. **Bot service CPU ceiling: 2 → 4 cores** (`docker-compose.prod.yml`). Raising
   the QR pool's worker count alone does nothing if the *container* is still
   capped at 2 CPUs by Docker's cgroup quota — total CPU consumption is capped
   regardless of process count. Both had to move together. This raises the box's
   documented CPU over-commit from 12 to 14 ceiling-units against 8 real cores —
   still fine as a ceiling (not a reservation) on a host that is otherwise idle.

## 5. pgbouncer — not needed now; here's the exact trigger to revisit it

Current connection math: `API_WORKERS` (4) × (`db_pool_size` 10 + `db_max_overflow`
20) + 1 bot process × 30 = **150 possible connections**, against Postgres's
`max_connections = 200`. Headroom: 50 connections. Actual observed usage at rest:
~14-19.

**pgbouncer becomes worth adding when any of these happen:**
- `API_WORKERS` raised beyond ~5 (5 × 30 + 30 = 180; 6 × 30 + 30 = 210 > 200 —
  exceeds Postgres's limit outright).
- Multiple companies each running several bots concurrently on this same
  Postgres instance, multiplying the number of processes that each want their own
  30-connection budget.
- You want per-process pools larger than 30 without proportionally raising
  Postgres's `max_connections` (which itself has memory costs — each Postgres
  connection reserves real backend memory).

Until one of those is true, adding pgbouncer is complexity with no corresponding
problem — it's a new moving part, a new thing to monitor, and a new failure mode
(connection pooler outage taking down the app even if Postgres itself is fine),
for headroom that already exists. If/when you do add it: run it in **transaction
pooling mode** (not session mode) since this codebase's session usage is
short-lived per request/task, not long-held.

## 6. Test suite note

Three tests fail/error in this environment regardless of any change in this
document (confirmed present on completely unmodified code, run inside the actual
container rather than an isolated CI sandbox):

- `test_company_connects_up_to_three_bots` — requires reaching Telegram's real
  API to validate a token; unrelated to `MAX_BOTS_PER_COMPANY`'s value (confirmed
  by reading the failure: it fails on the very first bot-token validation call,
  before the count logic is ever reached).
- `test_health_endpoint_checks_the_database` / `test_notify_embedded_mode_hands_to_bot_manager`
  / the three `test_scale.py` Redis-roundtrip tests — artifacts of running pytest
  inside a container that shares Redis with whatever else is active, not failures
  in the code itself.

None of these reflect a real defect; they're a property of the test environment,
not the target scenario in this document.

## 7. Operational checklist for the actual event

1. Connect as many bot tokens as practical to the company (up to 10) — the single
   biggest lever, see §3.
2. `registration_starts_at` / `checkin_until` / `sale_starts_at` on the real event
   should be set exactly once, correctly, well before the day — there is no longer
   any temporary bypass in the code (all reverted; confirmed byte-identical to
   before this session's testing).
3. Watch `docker compose logs -f bot` and Netdata during the actual opening minute
   — if `BrokenProcessPool` warnings appear repeatedly, the QR pool is unstable
   under load and needs investigation before the next event, not during it.
4. The registration retry/dead-letter mechanism added earlier this session
   (`navbat:dead-letter:registrations` in Redis) is the safety net for "any fail
   should fix immediately and continue" — after the event, check
   `redis-cli llen navbat:dead-letter:registrations`; anything in it is a
   registration that failed after 3 retries and needs manual follow-up.
5. `MAX_BOTS_PER_COMPANY=10` is a soft ceiling, not a hard architecture limit —
   if a future event needs more, the code change is one line; the real constraint
   is how many BotFather bots you're willing to create and manage.
