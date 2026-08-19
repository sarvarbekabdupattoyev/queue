# Security rules — SmartNavbat

Read this whenever a change touches auth, input, uploads, tokens, secrets,
webhooks, WebSockets, headers, rate limits, or adds an endpoint. These are
requirements, not suggestions.

## Identity & auth

- Passwords: bcrypt only (via `hash_password_async`), never logged, never in
  responses except the one-time generated employee password. Login errors are
  uniform ("Telefon raqam yoki parol noto'g'ri") — never reveal whether the
  phone exists.
- JWT: HS256 with `SECRET_KEY`; only the user id in `sub`; always check
  `is_active` on load. No roles inside the token — roles come from the DB so
  revocation is immediate. Tokens never appear in logs.
- Every non-public route declares a role dependency. New route = explicit
  decision: public / staff / manager / owner. "Forgot to protect" is the
  default failure — grep new routes for a `require_roles` or public rationale.

## Multi-tenancy (the SaaS boundary)

- Every read/write of company-owned data filters by the caller's
  `company_id`. Existence of foreign resources must not leak: return 404,
  same body/timing as truly missing.
- Public surfaces expose the minimum: display state = letter codes plus, by
  product decision, waiting clients' names and bot registration times — never
  phones, chat ids or ticket QR codes; ticket page keyed by unguessable code
  (never sequential ids in URLs).

## Input handling

- All input passes through Pydantic schemas with length caps; phones through
  `normalize_phone`. No f-string SQL ever — SQLAlchemy expressions only.
- Uploads: allow-list content types, size cap (`max_logo_size`), server-side
  generated filenames (`secrets.token_hex`), stored outside the web root and
  served via the static mount only. Never trust the client filename.
- Anything rendered into Telegram messages or logs from user input is plain
  text — no HTML parse mode with user content interpolated.

## Secrets & tokens

- Secrets (SECRET_KEY, DB/Redis URLs, bot tokens) live in env only — never in
  code, tests, README examples, or commits. `.env` is gitignored.
- Telegram bot tokens are tenant credentials: never returned via the API
  (only `has_bot_token` + username), never logged.
- Webhook auth: per-company HMAC-derived secret validated with
  `hmac.compare_digest` (constant time). Rejections are indistinguishable
  (same 403) for unknown company vs bad secret.

## Network surface

- nginx is the only public entry: rate limits stay on (`/api` 20 r/s,
  `/api/auth` 5 r/s per IP) — any new sensitive endpoint gets a limit review.
- WebSockets: staff sockets authenticate via token and verify company
  membership BEFORE `accept()`; public sockets only by unguessable code.
- Production is HTTPS-only (camera + Telegram webhooks require it);
  cookies are not used — no CSRF surface, keep it that way or add CSRF
  protection with the change.
- CORS: explicit origin list from settings; never `*` with credentials.

## Operational

- Dependencies: pinned ranges in `pyproject.toml`/`package-lock.json`;
  adding one requires a maintenance/health check.
- Logs carry ids, not personal data bundles; no password/token/QR-code
  values in logs at any level.
- On any suspicion of a leaked secret: rotate (SECRET_KEY invalidates all
  sessions — that is acceptable), revoke bot token via BotFather.
