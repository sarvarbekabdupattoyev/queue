# Frontend rules — SmartNavbat (read before touching frontend/)

React 18 + TypeScript (strict) + Vite + TanStack Query. The root `CLAUDE.md`
invariants apply on top of these.

## Languages

- The **operational app** (dashboard, panels, display, ticket page) is Uzbek.
- The **marketing/auth surfaces** (landing `/`, login, register) are
  trilingual via `src/i18n` (uz default / en / ru, persisted `sn_lang`).
  Any new string there is added to ALL THREE dicts — `Dict` typing enforces
  it; never hardcode text in those components.
- Landing/auth animations use the `motion` package plus the ReactBits-style
  components in `src/landing/bits/` — those surfaces are lazy-loaded chunks;
  never import `motion` into the eager app bundle.

## Design system rules (the look is a feature — protect it)

- **Tokens only.** Every color, radius, shadow, and font comes from the CSS
  custom properties in `src/styles.css`. Never hardcode hex values or
  `px` shadows in components; if a token is missing, add it to BOTH themes.
- Type is two-voice: `--display` (Instrument Serif) for page titles, card
  titles and big numbers; `--body` (Inter) for everything else. Solid pastel
  fills pair with the fixed `--on-pastel-*` inks (pastels stay light in both
  themes); translucent `--tint-*-bg` chips pair with `--tint-*-text`.
- Charts are the hand-rolled SVG primitives in `src/components/charts.tsx`
  (BarChart / LineChart / Donut) — extend those, never add a chart library.
- **Light and dark are equal citizens.** `:root` defines light,
  `[data-theme="dark"]` overrides. Any new UI must be checked in both themes
  before it ships. Theme selection lives in `src/theme/ThemeContext.tsx`
  (light / dark / system, persisted); never read `prefers-color-scheme`
  ad hoc in components.
- **Exception:** the public TV display (`DisplayPage`) is always dark by
  design (it's a broadcast screen) — it uses its own fixed tokens. The
  landing hero board mock, the auth brand panel and the landing CTA reuse
  that always-bottle treatment with scoped constants in `landing.css`.
- **Icons are inline SVG** from `src/components/icons.tsx` (24×24 viewBox,
  `stroke="currentColor"`, `strokeWidth={1.8}`). Never emoji in chrome/UI;
  emoji are allowed only inside Telegram bot copy.
- Minimalism: default to whitespace over dividers, one accent per view,
  soft elevation (`--shadow-*`) in light / hairline borders in dark. Radius
  scale: `--r-sm/md/lg`. Motion: 120–200 ms ease; respect
  `prefers-reduced-motion`.

## UX rules

- Every async view has all four states designed: loading (skeleton or
  spinner), empty (helpful text + next action), error (human Uzbek message),
  success. No blank screens.
- Destructive actions confirm; passwords/one-time secrets are shown once
  with an explicit copy button. Buttons show busy state and disable while
  pending — no double submits.
- Live screens (manager, scanner, display, event detail) must keep working
  when the WebSocket drops: `useLiveState` already reconnects + polls —
  always show the connection state where operators can see it.
- Touch targets on staff screens (manager/scanner) ≥ 44px; the primary
  action is the biggest thing on the screen.
- All text through Uzbek (latin) with sentence case; numbers use
  `font-variant-numeric: tabular-nums` (`.mono`).

## Code rules

- Server state = TanStack Query (`queryKey` per resource, invalidate after
  mutations); UI state = local `useState`. No global state library, no
  ad-hoc `fetch` — always the `api()` client (it handles auth + errors).
- Components stay small and typed; shared primitives live in
  `src/components/ui.tsx` — extend them instead of one-off styling.
- Routing: role-gated via `Protected` in `App.tsx`. New pages register
  there and in the sidebar/nav where relevant.
- `npx tsc -b` (strict, noUnusedLocals) and `npx vite build` must be clean
  before finishing. No `any` unless annotated with a reason.

## Accessibility

- Interactive elements are real `<button>`/`<a>`/`<label>`; every input has
  a label; modals trap Escape and mark `aria-modal`; focus states use the
  token ring (`--ring`), never `outline: none` without replacement.
- Color contrast ≥ 4.5:1 for text in both themes (check tints on badges).
