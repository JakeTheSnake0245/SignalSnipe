#!/usr/bin/env bash
set -euo pipefail

if [[ ${EUID:-$(id -u)} -ne 0 ]]; then
  echo "Run as root: sudo ./install.sh"
  exit 1
fi

REPO_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
APP_DIR="/opt/signalsnipe"
ETC_DIR="/etc/signalsnipe"
LOG_DIR="/var/log/signalsnipe"
USER_NAME="signalsnipe"

echo "[1/10] Installing OS packages..."
apt-get update
apt-get install -y \
  git \
  python3 python3-venv python3-pip python3-dev \
  build-essential \
  rtl-sdr librtlsdr0 \
  udev

echo "[2/10] Creating user (${USER_NAME}) if needed..."
if ! id -u "${USER_NAME}" >/dev/null 2>&1; then
  useradd -r -m -s /usr/sbin/nologin "${USER_NAME}"
fi

echo "[3/10] Creating directories..."
mkdir -p "${APP_DIR}" "${ETC_DIR}" "${LOG_DIR}"
chown -R "${USER_NAME}:${USER_NAME}" "${LOG_DIR}"

echo "[4/10] Deploying application files to ${APP_DIR}..."
rm -rf "${APP_DIR}"
mkdir -p "${APP_DIR}"

# Copy repo content
cp -a "${REPO_DIR}/app" "${APP_DIR}/"
cp -a "${REPO_DIR}/web" "${APP_DIR}/"
cp -a "${REPO_DIR}/scripts" "${APP_DIR}/"
cp -a "${REPO_DIR}/run-scan.sh" "${APP_DIR}/run-scan.sh"

# Prefer scripts/run-*.sh as canonical launchers
if [[ -f "${APP_DIR}/scripts/run-scan.sh" ]]; then
  cp -a "${APP_DIR}/scripts/run-scan.sh" "${APP_DIR}/run-scan.sh"
fi
if [[ -f "${APP_DIR}/scripts/run-web.sh" ]]; then
  cp -a "${APP_DIR}/scripts/run-web.sh" "${APP_DIR}/run-web.sh"
fi

chmod +x "${APP_DIR}/run-scan.sh" "${APP_DIR}/run-web.sh" 2>/dev/null || true
chown -R "${USER_NAME}:${USER_NAME}" "${APP_DIR}"

echo "[5/10] Creating Python venv + installing requirements..."
python3 -m venv "${APP_DIR}/venv"
"${APP_DIR}/venv/bin/pip" install --upgrade pip wheel
"${APP_DIR}/venv/bin/pip" install -r "${REPO_DIR}/requirements.txt"

echo "[6/10] Installing default config (if missing)..."
if [[ ! -f "${ETC_DIR}/config.json" ]]; then
  cp -a "${REPO_DIR}/config/config.example.json" "${ETC_DIR}/config.json"
  chown "${USER_NAME}:${USER_NAME}" "${ETC_DIR}/config.json"
  chmod 0644 "${ETC_DIR}/config.json"
else
  echo "  - Keeping existing ${ETC_DIR}/config.json"
fi

echo "[7/10] Optional DVB blacklist (prevents kernel grabbing RTL stick)..."
BL="/etc/modprobe.d/rtl-sdr-blacklist.conf"
if [[ ! -f "${BL}" ]]; then
  cat > "${BL}" <<'EOBL'
blacklist dvb_usb_rtl28xxu
blacklist rtl2832
blacklist rtl2830
EOBL
fi

echo "[8/10] Installing systemd services..."
install -m 0644 "${REPO_DIR}/systemd/signalsnipe-scan.service" /etc/systemd/system/signalsnipe-scan.service
install -m 0644 "${REPO_DIR}/systemd/signalsnipe-web.service"  /etc/systemd/system/signalsnipe-web.service

systemctl daemon-reload

echo "[9/10] Enabling + starting services..."
systemctl enable --now signalsnipe-scan.service signalsnipe-web.service

echo "[10/10] Done."
echo "Web UI: http://<pi-ip>:8088"
echo "Logs:"
echo "  journalctl -u signalsnipe-scan.service -n 50 --no-pager"
echo "  journalctl -u signalsnipe-web.service  -n 50 --no-pager"
