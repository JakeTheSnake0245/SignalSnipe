<img width="2510" height="1393" alt="image" src="https://github.com/user-attachments/assets/a2de2f79-c628-46b6-b5ea-58a01f0a1ade" />

# SignalSnipe

RF scanner that uses `rtl_power` for sweeping and emits TAK CoT + GeoChat UDP messages.

## What’s in here
- `app/main.py` – scanner + detection + CoT + GeoChat
- `run-scan.sh` – service launcher
- `systemd/` – unit + overrides
- `config/config.example.json` – example config (sanitized)

## Install (high level)
1. Install deps (rtl-sdr tools + python venv deps)
2. Place config at `/var/lib/signalsnipe/config.json`
3. Install systemd unit + enable service

## Version
- Tag: v1.5.5

## Defaults (from systemd overrides)
- Config path: `/var/lib/signalsnipe/config.json` (SIGNALSNIPE_CONFIG)
- Web bind: `0.0.0.0:8088` (GUNICORN_BIND)
