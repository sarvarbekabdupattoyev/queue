#!/usr/bin/env bash
# SmartNavbat — one-time server bootstrap for Ubuntu 24.04 LTS.
# Prepares the OS (clock, kernel, firewall, Docker, swap, backups dir) for the
# stack in docker-compose.yml + docker-compose.prod.yml.
#
#   sudo bash deploy/setup-server.sh
#
# Safe to re-run: every step checks before it changes anything.
# After it finishes, follow the "NEXT STEPS" it prints (TLS, .env, compose up)
# — full walkthrough in docs/PRODUCTION_SERVER_SETUP.md.

set -euo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

say() { printf '\n\033[1;32m== %s\033[0m\n' "$*"; }

[ "$(id -u)" -eq 0 ] || { echo "Run as root: sudo bash deploy/setup-server.sh" >&2; exit 1; }

say "Base packages + clock (chrony is NOT optional: checkin_until is a server-clock decision)"
export DEBIAN_FRONTEND=noninteractive
apt-get update -q
apt-get install -yq chrony ufw fail2ban unattended-upgrades curl git ca-certificates certbot
timedatectl set-timezone Asia/Tashkent
chronyc tracking | grep -E "Leap status" || true

say "Kernel tuning (sysctl)"
install -m 0644 "$REPO_DIR/deploy/sysctl/99-smartnavbat.conf" /etc/sysctl.d/99-smartnavbat.conf
sysctl --system >/dev/null

say "Transparent Huge Pages -> madvise"
install -m 0644 "$REPO_DIR/deploy/systemd/thp-madvise.service" /etc/systemd/system/thp-madvise.service
systemctl daemon-reload
systemctl enable --now thp-madvise

say "8 GB swap safety net (kept unused by vm.swappiness=10)"
if ! swapon --show | grep -q /swapfile; then
  fallocate -l 8G /swapfile
  chmod 600 /swapfile
  mkswap /swapfile
  swapon /swapfile
  grep -q '^/swapfile' /etc/fstab || echo '/swapfile none swap sw 0 0' >> /etc/fstab
fi

say "Firewall: SSH + 80 + 443 only (and ONLY nginx publishes ports in compose)"
ufw allow OpenSSH >/dev/null
ufw allow 80/tcp >/dev/null
ufw allow 443/tcp >/dev/null
ufw --force enable

say "Docker Engine + Compose v2"
if ! command -v docker >/dev/null; then
  install -m 0755 -d /etc/apt/keyrings
  curl -fsSL https://download.docker.com/linux/ubuntu/gpg -o /etc/apt/keyrings/docker.asc
  chmod a+r /etc/apt/keyrings/docker.asc
  echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] \
https://download.docker.com/linux/ubuntu $(. /etc/os-release && echo "$VERSION_CODENAME") stable" \
    > /etc/apt/sources.list.d/docker.list
  apt-get update -q
  apt-get install -yq docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
fi

say "Docker daemon: capped logs, raised nofile, live-restore"
cat > /etc/docker/daemon.json <<'JSON'
{
  "log-driver": "json-file",
  "log-opts": { "max-size": "10m", "max-file": "3" },
  "default-ulimits": { "nofile": { "Name": "nofile", "Hard": 65535, "Soft": 65535 } },
  "live-restore": true
}
JSON
systemctl restart docker

say "journald capped at 500 MB (64 GB disk)"
mkdir -p /etc/systemd/journald.conf.d
printf '[Journal]\nSystemMaxUse=500M\n' > /etc/systemd/journald.conf.d/99-smartnavbat.conf
systemctl restart systemd-journald

say "Backup directories + nightly cron"
mkdir -p /opt/backups/weekly /var/www/certbot
install -m 0644 "$REPO_DIR/deploy/cron/smartnavbat" /etc/cron.d/smartnavbat

say "SSH hardening reminder"
echo "Set 'PasswordAuthentication no' + 'PermitRootLogin prohibit-password' in /etc/sshd_config"
echo "AFTER confirming your SSH key works, then: systemctl reload ssh  (fail2ban's sshd jail is already on)"

cat <<NEXT

======================================================================
NEXT STEPS (docs/PRODUCTION_SERVER_SETUP.md has the full detail)

1. TLS — nginx will not start without certificates:
     certbot certonly --standalone -d smartnavbat.uz -d www.smartnavbat.uz
2. Configuration:
     cd $REPO_DIR && cp .env.example .env   # then fill in the secrets
3. Start the stack:
     docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d --build
     docker compose -f docker-compose.yml -f docker-compose.prod.yml ps   # all "healthy"
4. Switch certbot renewals to webroot + reload hook (see the doc, §7).
======================================================================
NEXT
