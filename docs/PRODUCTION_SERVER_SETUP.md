# SmartNavbat — Production Server Setup

**Single node · 10,000-user registration burst · free / open-source components only**

| | |
|---|---|
| Host | `EU-DEDICATED-CLOUD-32` — AMD EPYC, 8 vCPU, 32 GB RAM, 64 GB NVMe |
| OS | Ubuntu 24.04 LTS |
| Stack | repo `docker-compose.yml` (postgres + redis + api + bot + frontend/nginx) + `docker-compose.prod.yml` override |
| Domain | `smartnavbat.uz` (Let's Encrypt TLS) |
| Requires | Docker Engine + Docker Compose **v2** (`docker compose`, not `docker-compose`) |

Everything referenced here is **in the repo**:

```
docker-compose.prod.yml            resource limits, tuned PG/Redis, healthchecks
deploy/nginx/prod.conf             TLS site config (mounted into the frontend container)
deploy/sysctl/99-smartnavbat.conf  kernel tuning
deploy/systemd/thp-madvise.service THP=madvise at boot
deploy/cron/smartnavbat            nightly DB + uploads backups, weekly prune
deploy/setup-server.sh             one-shot OS bootstrap (runs all of §2–§3)
.env.example                       the exact variables this stack reads
```

---

## 0. Capacity model — read this before touching anything

"10,000 users press `/start` within seconds" is three very different stages, and only two of them are ours:

| Stage | Who limits it | Rate on this box (tuned) | Time for 10,000 |
|---|---|---|---|
| 1. Absorb the webhook burst (nginx → bot service → HTTP 200 to Telegram) | us | ~2,000–3,000 req/s | **3–5 s** |
| 2. Process + persist registrations (FSM, ticket insert, code allocation) | us (PostgreSQL) | ~800–1,200 reg/s | **~10–15 s** |
| 3. Send replies + QR photos back | **Telegram: ~30 msg/s per bot — hard cap** | 25 msg/s per bot (built-in throttle) | see below |

Stage 3 is Telegram's per-bot delivery limit. No server changes it. SmartNavbat has **two levers built in**:

- **Parallel bots.** A company connects up to **3 bots** (Settings → Telegram botlar); all run the same registration flow against the same queue. 3 bots × 25 msg/s = **75 msg/s** outbound — a full 4–5-message dialogue for 10,000 users (~40–50k sends) drains in **~10 minutes** instead of ~30. Advertise all bot links so clients spread out.
- **Per-bot outbound throttle** (`app/services/telegram/throttle.py`): every bot's session paces `send*` calls at 25/s and **obeys `retry_after`** with bounded retries, so a flood-control response never becomes a silently lost QR code.

> **Correction to the earlier draft of this document:** it warned that a "4-digit ticket space (1000–9999)" holds only 9,000 numbers. SmartNavbat does not use digits — ticket codes are **random 4-letter uppercase codes (A–Z)**: 26⁴ = **456,976 codes per event**, allocated by random pick + DB unique constraint with retry. There is no capacity blocker at 10k, and no number-pool mechanism is needed.

### What the codebase already does for the burst

- Webhook ingest is **validate → schedule → 200**: constant-time HMAC secret check, then the update is processed in semaphore-bounded tasks (`BOT_MAX_CONCURRENT_UPDATES`), so Telegram is ACKed instantly and never re-sends because we're slow.
- Webhooks register with **`max_connections=100`** (Telegram's max; default is 40) and `allowed_updates` narrowed to what the bot actually handles.
- QR PNGs render in a **process pool** — a burst never serializes on the event loop; the ticket photo carries the code in large print.
- bcrypt runs off-loop; WS broadcasts are **debounced** (~200 ms) so 1,000 mutations produce ~5 pushes/s per event, not 1,000.
- FSM state lives in **Redis** (AOF) — a bot-service restart mid-dialogue loses at most the current step, never a ticket.
- `uvicorn[standard]` ships **uvloop** — both services already run on it, no extra setup.
- Health: **`GET /api/health`** and bot **`GET /healthz`** actually probe the DB (`SELECT 1`) and Redis (`PING`) and return 200/503 — wired into the compose healthchecks.
- `/start` is idempotent: a registered user gets their existing ticket re-sent, never a duplicate.

### Known limitation (accepted, documented)

Queue notifications (called / skipped / sale-started) go from API workers to the bot service over **Redis pub/sub — fire-and-forget**. If the bot service is down at the moment of publishing, those messages are not replayed. In practice the client always has a pull path (`/holat`, `/navbat`, the ticket web page), and the TV display shows every call. A durable Redis-Streams outbound queue is the natural next step if an event ever demonstrates real loss; do not build it speculatively.

---

## 1. Resource budget (8 vCPU / 32 GB / 64 GB NVMe)

Enforced by `docker-compose.prod.yml`:

| Component | CPU ceiling | Memory ceiling | Notes |
|---|---|---|---|
| PostgreSQL 16 | 4 | 12 GB | `shared_buffers` 6 GB; the rest is its page cache |
| Redis 7 | 1 | 2.5 GB | `maxmemory 2gb`, AOF, **noeviction** |
| API (uvicorn ×`API_WORKERS`) | 4 | 3 GB | staff panels, WS, public pages |
| Bot service ×1 (+ QR process pool) | 2 | 1.5 GB | the burst-path process |
| frontend (nginx) | 1 | 256 MB | TLS, SPA, WS upgrade, micro-cache |
| OS + free page cache + headroom | — | ~12 GB | free RAM is PostgreSQL's read cache |

CPU limits deliberately over-commit (they sum to >8): they are **ceilings** that stop one component starving the box, not reservations — the scheduler shares idle cores.

Disk plan (64 GB is tight — hygiene in §10): OS + Docker ≈ 15 GB, images ≈ 5 GB, PostgreSQL data + WAL ≤ 8 GB, Redis AOF ≤ 1 GB, logs (rotated) ≤ 2 GB → keep **≥ 25 GB free**, alert at 80 % used.

---

## 2. Operating system (Ubuntu 24.04 LTS)

Everything in this section is automated — run once from the repo root:

```bash
sudo bash deploy/setup-server.sh
```

What it does (and why), so you can audit it:

- **`chrony` + `Asia/Tashkent`** — *not optional*: `checkin_until` and `sale_starts_at` are server-clock decisions. A drifting clock opens or closes the queue at the wrong minute in front of a full reception hall. Verify: `chronyc tracking` shows "Leap status: Normal".
- **Kernel** (`deploy/sysctl/99-smartnavbat.conf` → `/etc/sysctl.d/`): deeper accept queues for the burst (`somaxconn=4096`, syn backlog 8192), faster port turnover for nginx→upstream and bot→api.telegram.org churn, `vm.overcommit_memory=1` (required by Redis AOF rewrite), `vm.swappiness=10`.
- **THP → madvise** (`deploy/systemd/thp-madvise.service`) — Redis and PostgreSQL latency.
- **8 GB swap** — exists only so the OOM killer never takes PostgreSQL down mid-event; `swappiness=10` keeps it unused otherwise.
- **UFW: 22/80/443 only.** The trap: Docker's published ports **bypass UFW** (Docker writes iptables directly). The rule that makes UFW meaningful: **only the `frontend` (nginx) service has `ports:` in compose** — postgres, redis, api and bot stay on the internal network. `docker-compose.prod.yml` keeps it that way; never add `ports:` to the others.
- **Docker daemon**: json-file logs capped at 3×10 MB per container (a burst writes a lot of lines; the disk is 64 GB), `nofile` 65535, `live-restore` so a dockerd restart doesn't kill containers. journald capped at 500 MB.
- **fail2ban** with the default `sshd` jail.
- **SSH**: the script *reminds* you (it will not lock you out itself) — set `PasswordAuthentication no` and `PermitRootLogin prohibit-password` in `/etc/ssh/sshd_config` after confirming your key works, then `systemctl reload ssh`.

---

## 3. First deploy — exact order

```bash
git clone <repo> /opt/smartnavbat && cd /opt/smartnavbat
sudo bash deploy/setup-server.sh

# 1) TLS FIRST — nginx refuses to start without certificate files:
sudo certbot certonly --standalone -d smartnavbat.uz -d www.smartnavbat.uz

# 2) configuration
cp .env.example .env
#    fill in: SECRET_KEY=$(openssl rand -hex 32)  POSTGRES_PASSWORD=$(openssl rand -hex 16)
#    keep BOT_WEBHOOK_BASE=https://smartnavbat.uz/tgwh (webhook mode)

# 3) up
docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d --build
docker compose -f docker-compose.yml -f docker-compose.prod.yml ps    # everything "healthy"

# 4) one-time: enable the query-statistics extension (preloaded in prod override)
docker compose -f docker-compose.yml -f docker-compose.prod.yml \
  exec -T postgres psql -U navbat -d navbat -c "CREATE EXTENSION IF NOT EXISTS pg_stat_statements;"

# 5) switch cert renewals to webroot (no downtime, forever-free) — §7
```

The database schema is created automatically on first start (`create_schema()`); companies then connect their bot tokens from the dashboard and the bot service picks them up via Redis — no restarts.

`.env` reference (all read by `backend/app/core/config.py` / compose):

| Variable | Prod value | Why |
|---|---|---|
| `SECRET_KEY` | `openssl rand -hex 32` | JWT signing + per-bot webhook HMAC secrets |
| `POSTGRES_PASSWORD` | `openssl rand -hex 16` | DB user `navbat`, database `navbat` |
| `API_WORKERS` | `4` | uvicorn workers in the api container |
| `DB_POOL_SIZE` / `DB_MAX_OVERFLOW` | `10` / `10` | connections = api 4×(10+10) + bot (10+10) = **100** ≤ `max_connections=200` — margin for psql, backups, monitoring |
| `TELEGRAM_ENABLED` | `1` | `0` only for CI / rehearsals without sends |
| `BOT_WEBHOOK_BASE` | `https://smartnavbat.uz/tgwh` | webhook mode; empty → long polling (dev) |
| `BOT_MAX_CONCURRENT_UPDATES` | `300` | far above the bot's DB pool **on purpose**: Telegram is already ACKed; excess handlers queue on our pool, not on Telegram's side |
| `CALL_TIMEOUT_MINUTES` | `3` | countdown shown to called clients |

---

## 4. PostgreSQL — why these values

(All set in `docker-compose.prod.yml`.) `shared_buffers=6GB` is generous for a dataset that stays in the low gigabytes for years — the whole working set lives in memory. `effective_cache_size=12GB` matches the **container's** memory limit, not host RAM: under cgroup v2 the container's page cache counts against its limit. `random_page_cost=1.1` and `effective_io_concurrency=200` tell the planner the truth about NVMe. `jit=off` because this is pure OLTP micro-queries — JIT warm-up costs more than it saves. `max_wal_size=4GB` caps WAL on the small drive; `checkpoint_completion_target=0.9` spreads checkpoint I/O so it never lands as a latency spike inside a burst.

**`synchronous_commit` stays on (default).** A queue platform must never confirm a code it can lose — a person shows up on sale day with a QR the database forgot. Under high insert concurrency PostgreSQL group-commits naturally and NVMe fsync keeps the per-commit cost small. Do not trade this for throughput you don't need — stage 3 (Telegram) is the bottleneck anyway.

After any event:

```sql
SELECT calls, mean_exec_time, total_exec_time, query
FROM pg_stat_statements ORDER BY total_exec_time DESC LIMIT 10;
```

## 5. Redis — why these values

Redis carries FSM registration state, WS fan-out, Telegram notify routing and bot-reload control. Two properties matter:

- **`noeviction`**: any eviction policy would *silently* drop half-finished registrations under memory pressure; `noeviction` fails loudly instead — and 2 GB is >100× the realistic need (10k FSM states are tens of megabytes).
- **AOF `everysec`**: bounds loss on a power cut to ≤1 s of acknowledged writes; Telegram redelivers anything we hadn't ACKed, so the worst case is a handful of users repeating one FSM step — never a lost ticket.

---

## 6. nginx — the parts that decide the burst

`deploy/nginx/prod.conf` (mounted over the frontend container's config). Decisions worth knowing before you edit it:

- **`/tgwh/` has NO per-IP `limit_req`. Ever.** Telegram funnels all 10,000 updates through a handful of its own IPs; the generic 20 r/s per-IP zone would throttle Telegram itself into retry loops on the most important path in the system. Defense-in-depth is the `geo` allowlist of Telegram's published ranges (`149.154.160.0/20`, `91.108.4.0/22` — verify at <https://core.telegram.org/bots/webhooks>); the real authentication is the per-bot HMAC secret checked constant-time in-app.
- Rate limits everywhere else: `/api/` 20 r/s, `/api/auth/` 5 r/s, `/api/public/` 60 r/s per IP.
- **1-second micro-cache on `/api/public/`** — 10,000 people refreshing their ticket page cost ~one upstream request per second; the WebSocket is the live channel, 1 s of staleness is invisible.
- WS locations **repeat the proxy headers**: `proxy_set_header` in a location cancels ALL inherited ones — that comment in the file is load-bearing, keep it.
- Only this container publishes ports (80/443) — see the UFW trap in §2.
- If you ever put Cloudflare's free tier in front (works fine with webhooks + WS): `$remote_addr` becomes Cloudflare's IP — remove the `geo` allowlist block and rely on the HMAC secret.

## 7. Free TLS, renewing forever

First issuance happens in §3 (standalone, before nginx runs). Then switch renewals to webroot so nothing ever has to stop:

```bash
sudo tee /etc/letsencrypt/renewal-hooks/deploy/reload-nginx.sh >/dev/null <<'HOOK'
#!/bin/sh
docker compose -f /opt/smartnavbat/docker-compose.yml -f /opt/smartnavbat/docker-compose.prod.yml exec -T frontend nginx -s reload
HOOK
sudo chmod +x /etc/letsencrypt/renewal-hooks/deploy/reload-nginx.sh

sudo certbot certonly --webroot -w /var/www/certbot \
  -d smartnavbat.uz -d www.smartnavbat.uz --force-renewal
sudo certbot renew --dry-run          # must pass
```

The systemd timer certbot ships with does the rest, free, forever.

---

## 8. Telegram webhooks — verification

The code registers every company bot at `BOT_WEBHOOK_BASE/{bot_id}` with `max_connections=100` and a per-bot HMAC secret derived from `SECRET_KEY`. Per bot, before a sale day:

```bash
curl -s "https://api.telegram.org/bot<TOKEN>/getWebhookInfo" | python3 -m json.tool
```

Must show: the correct `https://smartnavbat.uz/tgwh/<bot_id>` URL, `"max_connections": 100`, and `"pending_update_count": 0` — that count is your single best "are we keeping up" metric during a burst (if it grows while local queues are empty, the bot container is down or nginx is misrouting `/tgwh/`; everything queued is redelivered once it's back).

For a big event, connect **2–3 bots** in Settings and advertise all their links — the outbound cap multiplies per token (§0).

---

## 9. Load test before the day (k6 — free)

Simulate **Telegram**, not your users: fire signed webhook POSTs at `/tgwh/{bot_id}`.

Get the bot's DB id and webhook secret (the secret is HMAC-derived, not stored):

```bash
docker compose -f docker-compose.yml -f docker-compose.prod.yml exec -T api \
  python -c "from app.services.telegram.manager import webhook_secret; print(webhook_secret(1))"
# "1" = the bot's id in company_bots (first connected bot of the first company = 1)
```

```javascript
// burst.js — simulate Telegram delivering /start updates
import http from 'k6/http';
import { check } from 'k6';

export const options = {
  scenarios: {
    burst: {
      executor: 'ramping-arrival-rate',
      startRate: 50, timeUnit: '1s',
      preAllocatedVUs: 2000, maxVUs: 4000,
      stages: [
        { target: 1500, duration: '10s' },  // ramp to 1,500 updates/s
        { target: 1500, duration: '10s' },  // ~15k+ updates delivered
        { target: 0,    duration: '5s'  },
      ],
    },
  },
};

const URL = `${__ENV.BASE}/tgwh/${__ENV.BOT_ID}`;

export default function () {
  const uid = 1000000 + Math.floor(Math.random() * 9000000);
  const body = JSON.stringify({
    update_id: uid,
    message: {
      message_id: 1,
      date: Math.floor(Date.now() / 1000),
      chat: { id: uid, type: 'private' },
      from: { id: uid, is_bot: false, first_name: 'LoadTest' },
      text: '/start',
    },
  });
  const res = http.post(URL, body, {
    headers: {
      'Content-Type': 'application/json',
      'X-Telegram-Bot-Api-Secret-Token': __ENV.TG_SECRET,
    },
  });
  check(res, { 'is 200': (r) => r.status === 200 });
}
```

```bash
docker run --rm -i \
  -e BASE=https://smartnavbat.uz -e BOT_ID=<bot_db_id> -e TG_SECRET=<secret> \
  grafana/k6 run - < burst.js
```

Rules of the rehearsal: use a **staging company** with a throwaway bot token (or `TELEGRAM_ENABLED=0`) so the consumer path runs without real sends; temporarily add the tester's IP to the nginx `geo` allowlist (the load test is not Telegram); rehearse the queue phase separately with the `/api/events/{id}/seed` endpoint; run the pytest suite against PostgreSQL (`TEST_DATABASE_URL=…`).

**Acceptance for a 10k event:** 10k+ synthetic `/start` in ≤10 s → all 200 · p99 webhook latency < 50 ms · zero 5xx · no container restart, no OOM · WS pushes stay debounced (~5/s per event) · `docker compose ps` all healthy afterwards.

---

## 10. Backups & 64 GB disk hygiene

Installed by the setup script as `/etc/cron.d/smartnavbat` (`deploy/cron/smartnavbat`):

- 02:00 nightly `pg_dump -Fc` → `/opt/backups/db-YYYY-MM-DD.dump`, 7 kept
- 02:20 nightly tar of the uploads volume (company logos), 7 kept
- Sunday: promote the day's dump to `/opt/backups/weekly/` (4 kept), prune Docker images older than a week

Off-site without paying: `rclone` the dump to Backblaze B2 or Cloudflare R2 free tier (a compressed dump of this schema is megabytes). **Test a restore monthly** — an untested backup is a rumor:

```bash
docker compose -f docker-compose.yml -f docker-compose.prod.yml exec -T postgres \
  bash -c 'createdb -U navbat restore_test && pg_restore -U navbat -d restore_test' < /opt/backups/db-<date>.dump
docker compose -f docker-compose.yml -f docker-compose.prod.yml exec -T postgres \
  psql -U navbat -d restore_test -c 'SELECT count(*) FROM tickets;'
docker compose -f docker-compose.yml -f docker-compose.prod.yml exec -T postgres \
  dropdb -U navbat restore_test
```

Disk stays bounded by design: WAL capped at 4 GB, container logs at 30 MB each, journald at 500 MB, weekly image prune. Alert at 80 % anyway.

## 11. Monitoring & alerting — free

**Netdata** — one container, auto-instruments PostgreSQL, Redis, nginx and every container. Bind to localhost, reach it over an SSH tunnel, never expose :19999:

```bash
docker run -d --name=netdata --pid=host --network=host \
  -v netdataconfig:/etc/netdata -v netdatalib:/var/lib/netdata -v netdatacache:/var/cache/netdata \
  -v /etc/passwd:/host/etc/passwd:ro -v /etc/group:/host/etc/group:ro \
  -v /proc:/host/proc:ro -v /sys:/host/sys:ro \
  -v /var/run/docker.sock:/var/run/docker.sock:ro \
  --restart unless-stopped netdata/netdata
# view: ssh -L 19999:localhost:19999 <server>  ->  http://localhost:19999
```

**External probe** — Uptime Kuma (self-hosted) or healthchecks.io free tier on `GET https://smartnavbat.uz/api/health` (real DB+Redis probe, 200/503).

The four numbers to watch during a burst: bot-service CPU · PostgreSQL active connections · `getWebhookInfo.pending_update_count` per bot · the rate of `Flood control on sendMessage` / `sendPhoto` warnings in `docker compose logs -f bot`. Occasional flood-control lines mean the throttle is riding the cap correctly; a constant stream means too few bots are connected for the audience size — add a second/third bot (§0).

---

## 12. Sale-day runbook

**T−1 day**

- `chronyc tracking` synced · `df -h` under 60 % · `docker compose ps` all healthy
- last night's dump exists **and restores** into a scratch database (§10)
- `certbot certificates` — more than 14 days remaining
- per company bot `getWebhookInfo`: correct URL, `max_connections: 100`, `pending_update_count: 0`
- expected turnout > ~5,000? Confirm 2–3 bots are connected and all bot links are in the announcements
- k6 burst against staging passes §9 acceptance; `curl -s https://smartnavbat.uz/api/health` returns `{"status":"ok",...}`

**T−0 (registration burst)**

Terminal 1: Netdata. Terminal 2: `docker compose logs -f bot`. The healthy picture at 10k: webhook POSTs spike and are all 200 inside seconds; QR photos drain at a steady ~25/s per bot; scattered flood-control retries; PG connections < 120; load average < 8. If Telegram's `pending_update_count` grows instead — the bot container is down or nginx is misrouting `/tgwh/`; everything queued is redelivered once it's back.

**T+1**

Skim `pg_stat_statements` (§4) for anything unexpected; check `docker compose logs bot | grep -c "Flood control"` to judge whether next time needs one more parallel bot. Nothing else — autovacuum owns the rest.

---

## Appendix — one-page checklist

```
OS        [ ] chrony synced       [ ] sysctl 99-smartnavbat applied  [ ] THP=madvise
          [ ] 8G swap             [ ] UFW 22/80/443 only             [ ] SSH keys-only
Docker    [ ] daemon.json (logs, ulimits, live-restore)              [ ] journald 500M
Compose   [ ] only `frontend` publishes ports                        [ ] all healthchecks green
          [ ] PG flags applied (SHOW shared_buffers; -> 6GB)         [ ] Redis noeviction+AOF
          [ ] pg_stat_statements extension created
TLS       [ ] certbot issued      [ ] renew --dry-run passes         [ ] reload hook executable
nginx     [ ] /tgwh/ has NO limit_req                                [ ] geo allowlist current
          [ ] WS location repeats proxy headers                      [ ] /api/public 1s micro-cache
Telegram  [ ] webhook max_connections=100 per bot                    [ ] pending_update_count: 0
          [ ] 2-3 bots connected for a big event
App       [ ] /api/health 200 from outside                           [ ] bot /healthz healthy
          [ ] .env: strong SECRET_KEY + POSTGRES_PASSWORD            [ ] BOT_WEBHOOK_BASE set
Ops       [ ] nightly pg_dump + uploads cron installed               [ ] monthly restore test done
          [ ] Netdata via SSH tunnel                                 [ ] disk alert at 80%
          [ ] k6 acceptance passed
```
