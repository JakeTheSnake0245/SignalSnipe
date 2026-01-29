#!/usr/bin/env bash
set -euo pipefail

# SignalSnipe v2.x installer for Ubuntu Server 22.04 LTS (Raspberry Pi friendly)
# Installs runtime to: /opt/signalsnipe
# State/config: /var/lib/signalsnipe/config.json
# Services: signalsnipe-web.service + signalsnipe-scan.service
#
# Usage:
#   sudo ./install.sh

if [[ "$(id -u)" -ne 0 ]]; then
  echo "ERROR: run as root (use: sudo ./install.sh)" >&2
  exit 1
fi

export DEBIAN_FRONTEND=noninteractive

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PREFIX="/opt/signalsnipe"
STATE_DIR="/var/lib/signalsnipe"
CFG="${STATE_DIR}/config.json"
USER_NAME="signalsnipe"
GROUP_NAME="signalsnipe"

say(){ echo "[SignalSnipe] $*"; }

say "Repo: $REPO_DIR"
say "Prefix: $PREFIX"
say "State:  $STATE_DIR"

say "=== A) APT deps (includes network-manager for nmcli) ==="
apt-get update -y
apt-get install -y --no-install-recommends \
  sudo \
  git rsync curl jq ca-certificates \
  python3 python3-venv python3-pip \
  build-essential pkg-config \
  rtl-sdr \
  sox ffmpeg \
  gpsd gpsd-clients \
  chrony \
  usbutils net-tools iw wireless-tools \
  network-manager

say "=== B) Service user ==="
if ! id -u "$USER_NAME" >/dev/null 2>&1; then
  useradd -m -s /bin/bash "$USER_NAME"
fi
if ! getent group "$GROUP_NAME" >/dev/null 2>&1; then
  groupadd "$GROUP_NAME" || true
fi
usermod -a -G "$GROUP_NAME" "$USER_NAME" || true

say "=== C) Install runtime to /opt ==="
mkdir -p "$PREFIX"
# Keep venv owned by root (safe), but app/web owned by service user is fine
rsync -a --delete --exclude "__pycache__/" --exclude "*.pyc" "$REPO_DIR/app/" "$PREFIX/app/" 2>/dev/null || true
rsync -a --delete --exclude "__pycache__/" --exclude "*.pyc" "$REPO_DIR/web/" "$PREFIX/web/" 2>/dev/null || true
if [[ -d "$REPO_DIR/scripts" ]]; then
  rsync -a --delete "$REPO_DIR/scripts/" "$PREFIX/scripts/"
fi
if [[ -f "$REPO_DIR/run-web.sh" ]]; then
  install -m 755 "$REPO_DIR/run-web.sh" "$PREFIX/run-web.sh"
elif [[ -f "$REPO_DIR/scripts/run-web.sh" ]]; then
  install -m 755 "$REPO_DIR/scripts/run-web.sh" "$PREFIX/run-web.sh"
fi
if [[ -f "$REPO_DIR/run-scan.sh" ]]; then
  install -m 755 "$REPO_DIR/run-scan.sh" "$PREFIX/run-scan.sh"
elif [[ -f "$REPO_DIR/scripts/run-scan.sh" ]]; then
  install -m 755 "$REPO_DIR/scripts/run-scan.sh" "$PREFIX/run-scan.sh"
fi

chown -R "$USER_NAME:$GROUP_NAME" "$PREFIX/app" "$PREFIX/web" "$PREFIX/scripts" 2>/dev/null || true
chmod -R u=rwX,g=rX,o= "$PREFIX/app" "$PREFIX/web" "$PREFIX/scripts" 2>/dev/null || true

say "=== D) Python venv + pip deps ==="
if [[ ! -x "$PREFIX/venv/bin/python3" ]]; then
  python3 -m venv "$PREFIX/venv"
fi
"$PREFIX/venv/bin/python3" -m pip install -U pip wheel setuptools

# Prefer requirements.txt if present in repo
if [[ -f "$REPO_DIR/requirements.txt" ]]; then
  "$PREFIX/venv/bin/pip" install -r "$REPO_DIR/requirements.txt"
else
  # Fallback minimal runtime deps
  "$PREFIX/venv/bin/pip" install Flask gunicorn mgrs
fi

say "=== E) State dir + config ==="
mkdir -p "$STATE_DIR"
chown "$USER_NAME:$GROUP_NAME" "$STATE_DIR"
chmod 750 "$STATE_DIR"

if [[ ! -f "$CFG" ]]; then
  # Try repo defaults first
  if [[ -f "$REPO_DIR/config/config.default.json" ]]; then
    install -m 640 -o "$USER_NAME" -g "$GROUP_NAME" "$REPO_DIR/config/config.default.json" "$CFG"
  elif [[ -f "$REPO_DIR/config.default.json" ]]; then
    install -m 640 -o "$USER_NAME" -g "$GROUP_NAME" "$REPO_DIR/config.default.json" "$CFG"
  else
    # Generate minimal config (includes device + location so UI doesn’t 500)
    "$PREFIX/venv/bin/python3" - <<'PY'
import json, os, socket
p="/var/lib/signalsnipe/config.json"
h=socket.gethostname()
cfg={
  "device": {"name": h, "callsign":"SignalSnipe", "uid": f"signalsnipe-{h[:8]}", "notes":""},
  "location": {"mode":"manual_latlon","lat":0.0,"lon":0.0,"alt":0.0,"mgrs":""},
  "tak": {"enabled": False, "server":"127.0.0.1","port":4242,"room":"SignalSnipe","target":"broadcast"},
  "scan": {"ranges":[{"start_hz":99000000,"end_hz":102000000,"step_hz":250000}], "interval_s":1, "gain_db":5.0, "threshold_db":-17.5},
  "baseline": {"enabled": False}
}
os.makedirs("/var/lib/signalsnipe", exist_ok=True)
with open(p,"w") as f: json.dump(cfg,f,indent=2); f.write("\n")
print("Wrote", p)
PY
    chown "$USER_NAME:$GROUP_NAME" "$CFG"
    chmod 640 "$CFG"
  fi
fi

say "=== F) systemd units ==="
cat > /etc/systemd/system/signalsnipe-web.service <<'UNIT'
[Unit]
Description=SignalSnipe Web UI (Flask/Gunicorn)
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=signalsnipe
Group=signalsnipe
Environment=SIGNALSNIPE_CONFIG=/var/lib/signalsnipe/config.json
Environment=GUNICORN_BIND=0.0.0.0:8088
ExecStart=/opt/signalsnipe/run-web.sh
Restart=always
RestartSec=2
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
UNIT

cat > /etc/systemd/system/signalsnipe-scan.service <<'UNIT'
[Unit]
Description=SignalSnipe RF Scanner (rtl_power + detection + CoT)
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=signalsnipe
Group=signalsnipe
Environment=SIGNALSNIPE_CONFIG=/var/lib/signalsnipe/config.json
ExecStart=/opt/signalsnipe/run-scan.sh
Restart=always
RestartSec=2
Nice=-5
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
UNIT

say "=== G) Allow web UI to run nmcli safely (no password) ==="
# Your logs show only these nmcli calls; keep sudoers tight and non-interactive.
cat > /etc/sudoers.d/signalsnipe-nmcli <<'SUDO'
Defaults:signalsnipe !requiretty
signalsnipe ALL=(root) NOPASSWD: /usr/bin/nmcli -t -f SSID,SECURITY,SIGNAL dev wifi list
signalsnipe ALL=(root) NOPASSWD: /usr/bin/nmcli -t -f DEVICE,TYPE,STATE dev status
signalsnipe ALL=(root) NOPASSWD: /usr/bin/nmcli -t -f DEVICE,STATE,CONNECTION dev status
signalsnipe ALL=(root) NOPASSWD: /usr/bin/nmcli -t -f ACTIVE,SSID,DEVICE dev wifi
signalsnipe ALL=(root) NOPASSWD: /usr/bin/nmcli dev wifi rescan
SUDO
chmod 440 /etc/sudoers.d/signalsnipe-nmcli
visudo -cf /etc/sudoers.d/signalsnipe-nmcli >/dev/null

say "=== H) Enable + start services ==="
systemctl daemon-reload
systemctl enable --now signalsnipe-web.service signalsnipe-scan.service

say "=== I) Quick verification ==="
sleep 2
systemctl is-active signalsnipe-web.service || true
systemctl is-active signalsnipe-scan.service || true
curl -sS -o /dev/null -w "HTTP %{http_code}\n" http://127.0.0.1:8088/ || true
sudo -u signalsnipe sudo -n /usr/bin/nmcli -t -f DEVICE,TYPE,STATE dev status || true

say "DONE."
