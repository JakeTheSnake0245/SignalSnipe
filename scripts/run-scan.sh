#!/usr/bin/env bash
set -euo pipefail
# export SIGNALSNIPE_CONFIG=/etc/signalsnipe/config.json
export SIGNALSNIPE_LOG=/var/log/signalsnipe/signalsnipe.log
source /opt/signalsnipe/venv/bin/activate
exec python3 -u /opt/signalsnipe/app/main.py
