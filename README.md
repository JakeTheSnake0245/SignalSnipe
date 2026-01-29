# SignalSnipe
<img width="373" height="702" alt="image" src="https://github.com/user-attachments/assets/a6fd914b-9c6d-4383-b2ac-8f5f5e3d1e46" />
<img width="1912" height="459" alt="image" src="https://github.com/user-attachments/assets/37e41ee0-e8ed-4d52-9035-5325169233b4" />
<img width="373" height="439" alt="image" src="https://github.com/user-attachments/assets/6b3474dd-873f-4c9b-bf03-5e525c3aa7d4" />
# SignalSnipe

SignalSnipe is a lightweight, field-friendly RF monitoring service built around **RTL-SDR** that continuously scans user-defined frequency ranges, detects signal activity, and pushes actionable alerts to a **web UI** and (optionally) **TAK** (CoT / GeoChat-style workflows). It’s designed to run well on small Linux SBCs (Raspberry Pi / Orange Pi) and stay operational in “real world” conditions: headless, boot-to-service, remote access, and simple recovery.

> **What it does well:** persistent scanning + “something lit up here” detection + human-friendly UI + integration-ready alert outputs.

---

## What’s inside

- **Scanner service**  
  Runs wideband sweeps using RTL-SDR tooling (e.g., `rtl_power`) and applies configurable detection logic (threshold/hold/cooldown, band profiles, etc.).

- **Web UI (Gunicorn)**  
  A simple dashboard to view scan status, detections, logs, and basic device controls.  
  Typical deployment: `gunicorn` bound to `0.0.0.0:8088`.

- **Systemd-managed**  
  Runs as services so it starts on boot and is easy to inspect/restart (`systemctl`, `journalctl`).

- **Network/Wi-Fi helper flow (optional)**  
  Supports environments where you want the device to be able to join Wi-Fi reliably, including “NetworkManager owns wlan0” setups.

---

## Supported platforms

This project targets:

- Ubuntu Server LTS on ARM64/ARMHF (Raspberry Pi 3B/4/5, Orange Pi family)
- Ubuntu Server LTS on x86_64 also works for development/testing

> **Note:** Driver/firmware behavior is hardware-specific. For Raspberry Pi onboard Wi-Fi (brcmfmac), NetworkManager + wpa_supplicant is recommended.

---

## Dependencies

### System packages (core)
These are the common OS-level requirements SignalSnipe expects (your install script should install these or equivalents):

- **Python 3** (and venv tooling)
  - `python3`, `python3-venv`, `python3-pip`
- **Build/utility tools**
  - `git`, `curl`, `ca-certificates`, `jq` (recommended), `build-essential` (if building native wheels)
- **RTL-SDR stack**
  - `rtl-sdr` (or `librtlsdr0` + `rtl-sdr` utilities depending on distro)
  - Tools commonly used: `rtl_test`, `rtl_power`
- **Service/runtime**
  - `systemd`
- **Networking (for Wi-Fi UI workflows)**
  - `network-manager`, `nmcli`
  - `wpasupplicant`
  - `dbus` (usually present by default)

### Python packages (core)
Installed into a virtual environment by the installer (typical):
- `flask` (or flask-compatible stack)
- `gunicorn`
- Other utilities your app imports (requests, pyyaml, numpy, etc. depending on your code)

### Optional dependencies (recommended depending on your use case)
- **ZeroTier**: remote management / overlay networking  
  - `zerotier-one`
- **TAK integration target**  
  - A reachable TAK Server / TCP/UDP CoT endpoint (varies by config)
- **GPS** (if you’re geotagging detections)
  - `gpsd` / `chrony` / NMEA GPS tooling depending on your setup

---

## Installation (recommended)

SignalSnipe is intended to be installed via the provided **install script** (the one you generated). The script should:

1. Install OS dependencies (RTL-SDR tooling, Python, NetworkManager bits as needed)
2. Create an application directory (commonly `/opt/signalsnipe`)
3. Create a Python virtual environment (commonly `/opt/signalsnipe/venv`)
4. Install Python requirements
5. Install/configure systemd services
6. Create/persist a configuration file (commonly `/var/lib/signalsnipe/config.json`)
7. Start and enable services

### Option A — Install from your script (local file)
If your installer lives in the repo:

```bash
git clone https://github.com/<yourname>/SignalSnipe.git
cd SignalSnipe
sudo bash ./install.sh
Option B — Install from a script you copied onto the device
sudo bash /path/to/your/install_script.sh
Tip: If you are installing on a headless SBC, keep an Ethernet cable plugged in during install to avoid Wi-Fi disruptions until services are up.

Services
Typical systemd units (names may vary depending on your installer):

signalsnipe-scan.service — scanner / detection engine

signalsnipe-web.service — web UI (gunicorn)

Start/stop/status
sudo systemctl status signalsnipe-web.service signalsnipe-scan.service --no-pager
sudo systemctl restart signalsnipe-web.service signalsnipe-scan.service
sudo systemctl enable --now signalsnipe-web.service signalsnipe-scan.service
Logs
sudo journalctl -u signalsnipe-web.service -n 200 --no-pager
sudo journalctl -u signalsnipe-scan.service -n 200 --no-pager
Web UI
By default (typical deployment), the Web UI listens on:

http://<device-ip>:8088

To find the active listening port:

sudo ss -ltnp | grep -E 'gunicorn|:8088'
Configuration
SignalSnipe reads configuration from a JSON file (commonly):

/var/lib/signalsnipe/config.json

This file typically includes sections like:

device (RTL-SDR gain, ppm, device index)

scan (frequency ranges, step size, thresholds, min duration, cooldown, hold time)

tak (TAK server IP/port, room name, enable/disable)

baseline (optional: noise floor / reference settings)

Your install script likely sets an environment variable like SIGNALSNIPE_CONFIG=/var/lib/signalsnipe/config.json in the web service.

RTL-SDR quick sanity checks
Dongle detection
rtl_test -t
Quick sweep test (example band)
out="/tmp/rtlpower_quick.csv"
rtl_power -f 162400000:162550000:25000 -i 1 -1 -g 18 "$out"
Wi-Fi notes (NetworkManager “owns wlan0”)
If you’re using Wi-Fi on Ubuntu Server images (especially Raspberry Pi), you may run into cases where wlan0 is marked unmanaged due to netplan/cloud-init defaults or existing rules.

SignalSnipe supports NetworkManager-based workflows. If you need to ensure NM controls Wi-Fi:

Confirm wpa_supplicant is installed and active

Confirm NM is managing the device:

nmcli -g GENERAL.NM-MANAGED,GENERAL.STATE,GENERAL.REASON device show wlan0
nmcli dev wifi list
Security considerations
This project interacts with RF scanning and network services. Treat devices as sensitive infrastructure.

Use strong SSH credentials/keys.

Restrict Web UI exposure (firewall or overlay network like ZeroTier).

Avoid running services as root unless necessary.

Troubleshooting
Web UI not loading
Check service:

sudo systemctl status signalsnipe-web.service --no-pager
sudo journalctl -u signalsnipe-web.service -n 200 --no-pager
Confirm port is listening:

sudo ss -ltnp | grep -E '8088|gunicorn'
No detections / scanner not running
Check scanner service logs:

sudo journalctl -u signalsnipe-scan.service -n 200 --no-pager
Confirm RTL-SDR is not in use by something else:

ps -ef | grep -E 'rtl_power|rtl_tcp|rtl_fm' | grep -v grep
Wi-Fi scan says “unavailable”
Confirm wpa_supplicant + dbus are active and NM is managing wlan0:

systemctl status wpa_supplicant --no-pager
systemctl is-active dbus
nmcli dev status
Roadmap / next steps
Band profiles (US common bands) with recommended gain/threshold/hold defaults

Better UI workflows for Wi-Fi “Use → fill SSID” and connect/disconnect

Cleaner export hooks for TAK, logs, and external event consumers

Multi-SDR coordination / distributed nodes (future)

Contributing
PRs welcome. If you’re contributing:

Keep changes small and testable

Prefer idempotent scripts

Add verification commands to docs when you add a feature

