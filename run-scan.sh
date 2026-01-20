#!/usr/bin/env bash
set -euo pipefail
# export SIGNALSNIPE_CONFIG=/etc/signalsnipe/config.json
export SIGNALSNIPE_LOG=/var/log/signalsnipe/signalsnipe.log
# (no activate) using venv executables directly
exec /opt/signalsnipe/venv/bin/python -u /opt/signalsnipe/app/main.py
