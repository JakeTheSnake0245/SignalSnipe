#!/usr/bin/env bash
set -euo pipefail

# Honor systemd Environment=SIGNALSNIPE_CONFIG=... if provided.
# Default to the same config the scanner uses.
: "${SIGNALSNIPE_CONFIG:=/var/lib/signalsnipe/config.json}"
export SIGNALSNIPE_CONFIG

# Honor systemd Environment=GUNICORN_BIND=... if provided.
: "${GUNICORN_BIND:=0.0.0.0:8088}"

# More resilient on slow SBCs: avoid single blocking sync worker
exec /opt/signalsnipe/venv/bin/gunicorn \
  -w 1 \
  -k gthread \
  --threads 4 \
  --timeout 120 \
  --graceful-timeout 30 \
  -b "${GUNICORN_BIND}" \
  web:app \
  --chdir /opt/signalsnipe/web
