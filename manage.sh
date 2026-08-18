#!/usr/bin/env bash
# NAVBAT — production topology: PostgreSQL + Redis (systemd) + API workers +
# separate bot service + Vite SPA + cloudflared tunnel.
# Detached with setsid so processes survive the launching shell.
set -uo pipefail
# Resolve project root from the script's own location (portable across hosts).
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")" && pwd)"
BACKEND="$ROOT/backend"
FRONTEND="$ROOT/frontend"
VENV="$BACKEND/.venv/bin"
API_WORKERS="${API_WORKERS:-4}"

start_infra() { systemctl start postgresql redis-server && echo "postgres+redis up"; }

start_api() {
  pgrep -f "[u]vicorn app.main:app" >/dev/null && { echo "api already up"; return; }
  cd "$BACKEND"
  setsid "$VENV/uvicorn" app.main:app --host 0.0.0.0 --port 8000 --workers "$API_WORKERS" \
    >"$ROOT/api.log" 2>&1 </dev/null & disown
  echo "api started ($API_WORKERS workers)"
}

start_bot() {
  pgrep -f "[b]ot_main:app" >/dev/null && { echo "bot already up"; return; }
  cd "$BACKEND"
  setsid "$VENV/uvicorn" app.bot_main:app --host 127.0.0.1 --port 8081 \
    >"$ROOT/bot.log" 2>&1 </dev/null & disown
  echo "bot started"
}

start_frontend() {
  pgrep -f "[v]ite preview" >/dev/null && { echo "frontend already up"; return; }
  cd "$FRONTEND"
  setsid ./node_modules/.bin/vite preview --port 5173 --host \
    >"$ROOT/frontend.log" 2>&1 </dev/null & disown
  echo "frontend started"
}

start_tunnel() {
  pgrep -f "[c]loudflared tunnel" >/dev/null && { echo "tunnel already up: $(cat "$ROOT/tunnel_url.txt" 2>/dev/null)"; return; }
  setsid cloudflared tunnel --no-autoupdate --url http://localhost:5173 \
    >"$ROOT/cloudflared.log" 2>&1 </dev/null & disown
  local url
  url=$(timeout 45 tail -n +1 -f "$ROOT/cloudflared.log" | grep -m1 -oE 'https://[a-z0-9-]+\.trycloudflare\.com')
  echo "$url" >"$ROOT/tunnel_url.txt"; echo "tunnel: $url"
}

case "${1:-status}" in
  start)   start_infra; start_api; start_bot; start_frontend; start_tunnel ;;
  stop)    pkill -f "[c]loudflared tunnel"; pkill -f "[v]ite preview"; pkill -f "[b]ot_main:app"; pkill -f "[u]vicorn app.main:app"; echo stopped ;;
  restart-backend)
    pkill -f "[b]ot_main:app"; pkill -f "[u]vicorn app.main:app"
    # wait for graceful exit before restarting (avoid pgrep seeing the dying procs)
    for _ in 1 2 3 4 5 6 7 8 9 10; do
      pgrep -f "[u]vicorn app.main:app" >/dev/null || pgrep -f "[b]ot_main:app" >/dev/null || break
      timeout 0.6 tail -f /dev/null 2>/dev/null || true
    done
    start_api; start_bot ;;
  url)     cat "$ROOT/tunnel_url.txt" 2>/dev/null || echo "no url yet" ;;
  status)
    for s in postgresql redis-server; do printf "%-14s %s\n" "$s:" "$(systemctl is-active "$s")"; done
    printf "%-14s %s\n" "api:"      "$(pgrep -f "[u]vicorn app.main:app" >/dev/null && echo up || echo down)"
    printf "%-14s %s\n" "bot:"      "$(pgrep -f "[b]ot_main:app"        >/dev/null && echo up || echo down)"
    printf "%-14s %s\n" "frontend:" "$(pgrep -f "[v]ite preview"        >/dev/null && echo up || echo down)"
    printf "%-14s %s\n" "tunnel:"   "$(pgrep -f "[c]loudflared tunnel"  >/dev/null && echo up || echo down)"
    printf "%-14s %s\n" "url:"      "$(cat "$ROOT/tunnel_url.txt" 2>/dev/null)"
    ;;
  *) echo "usage: $0 {start|stop|restart-backend|status|url}" ;;
esac
