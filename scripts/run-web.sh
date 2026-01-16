#!/usr/bin/env bash
set -euo pipefail
export SIGNALSNIPE_CONFIG=/etc/signalsnipe/config.json
source /opt/signalsnipe/venv/bin/activate

# More resilient on slow SBCs: avoid single blocking sync worker
exec gunicorn \
  -w 1 \
  -k gthread \
  --threads 4 \
  --timeout 120 \
  --graceful-timeout 30 \
  -b 0.0.0.0:8088 \
  web:app \
  --chdir /opt/signalsnipe/web
