#!/usr/bin/env bash
set -euo pipefail

if [[ ${EUID:-$(id -u)} -ne 0 ]]; then
  echo "Run as root: sudo ./uninstall.sh"
  exit 1
fi

systemctl disable --now signalsnipe-scan.service signalsnipe-web.service 2>/dev/null || true
rm -f /etc/systemd/system/signalsnipe-scan.service /etc/systemd/system/signalsnipe-web.service
systemctl daemon-reload 2>/dev/null || true

rm -rf /opt/signalsnipe

echo "Removed /opt/signalsnipe"
echo "Left configs/logs in:"
echo "  /etc/signalsnipe"
echo "  /var/log/signalsnipe"
