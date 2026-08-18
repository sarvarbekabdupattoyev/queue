# Code review rules — SmartNavbat

Self-review every change against this list before declaring it done. Review
like a senior who will be paged when it breaks at 09:00 on a sale day.

## Correctness first

- [ ] Does the change do exactly what was asked — no more, no less? Scope
      creep is a bug.
- [ ] Walk one concrete happy path AND one failure path through the new code
      by hand (wrong input, missing row, double click, network drop).
- [ ] Concurrency: what happens when two requests hit this at once? Unique
      constraints + retry beat check-then-act. Anything after `rollback()`
      must not touch expired ORM objects.
- [ ] Time: all comparisons in UTC-aware datetimes; boundary behavior at
      exactly `checkin_until` is deliberate and tested.
- [ ] Both runtime modes still work (single-process dev, Redis multi-process).

## Tests

- [ ] New behavior has a test that fails without the change.
- [ ] `cd backend && pytest -q` green; frontend `tsc -b` + `vite build` clean.
- [ ] Queue-rule changes: ordering, permission, and tenant-isolation tests
      updated, run on SQLite and (when DB-related) PostgreSQL.

## Simplicity & reuse

- [ ] Could this reuse an existing service/helper/component instead of a new
      one? (`queue_service`, `ui.tsx`, `icons.tsx`, deps in `api/deps.py`.)
- [ ] No dead code, no commented-out blocks, no TODOs without an issue.
- [ ] Names say what things are; functions fit on a screen; no clever
      one-liners that need a comment to decode.

## Performance (this app has a burst profile)

- [ ] No N+1 queries; new list endpoints are paginated/limited.
- [ ] Nothing CPU-heavy or blocking added to the event loop.
- [ ] Broadcasts stay debounced; no per-item broadcast/notify loops.
- [ ] Frontend: no unnecessary re-renders on 1 Hz timers (keep tick state
      local), query keys stable, lists keyed by id.

## Consistency

- [ ] Errors: Uzbek for users, English for logs; correct status codes
      (400 domain, 401 auth, 403 role, 404 missing-or-foreign, 409 conflict).
- [ ] UI uses tokens + shared components; checked in light AND dark.
- [ ] README / API table / .env.example updated when surface changed.

## Security gate

- [ ] If the change touches auth, input parsing, uploads, tokens, secrets,
      webhooks, WS, or headers — go through `docs/rules/security.md` line by
      line. If it doesn't, state that explicitly to yourself and move on.
