# SignalSnipe v2.0 — Setup Notes (Generated on Pi)

## Timestamp
```
2026-01-29T18:25:25.278057
```

## System
```
Linux signalsnipe 5.15.0-1092-raspi #95-Ubuntu SMP PREEMPT Mon Nov 24 23:13:38 UTC 2025 aarch64 aarch64 aarch64 GNU/Linux

PRETTY_NAME="Ubuntu 22.04.5 LTS"
NAME="Ubuntu"
VERSION_ID="22.04"
VERSION="22.04.5 LTS (Jammy Jellyfish)"
VERSION_CODENAME=jammy
ID=ubuntu
ID_LIKE=debian
HOME_URL="https://www.ubuntu.com/"
SUPPORT_URL="https://help.ubuntu.com/"
BUG_REPORT_URL="https://bugs.launchpad.net/ubuntu/"
PRIVACY_POLICY_URL="https://www.ubuntu.com/legal/terms-and-policies/privacy-policy"
UBUNTU_CODENAME=jammy
```

## Install Paths
- Repo: `/home/signalsnipe/SignalSnipe`
- Runtime: `/opt/signalsnipe`
- Config/state: `/var/lib/signalsnipe/config.json`
- systemd overrides: `/etc/systemd/system/signalsnipe-*.service.d/`

## APT Packages (useful subset)
```
awk: cmd. line:1: {print $2\" \" $3}
awk: cmd. line:1:          ^ backslash not last character on line
awk: cmd. line:1: {print $2\" \" $3}
awk: cmd. line:1:          ^ syntax error
```

## Python (SignalSnipe venv)
```
Python 3.10.12

blinker==1.9.0
click==8.3.1
Flask==3.1.2
gunicorn==24.1.1
itsdangerous==2.2.0
Jinja2==3.1.6
MarkupSafe==3.0.3
mgrs==1.5.3
packaging==26.0
Werkzeug==3.1.5
```

## systemd Units
```
Failed to list unit files: Connection timed out
```

### signalsnipe-web.service
```

```

### signalsnipe-scan.service
```
# /etc/systemd/system/signalsnipe-scan.service
[Unit]
Description=SignalSnipe RF Scanner (rtl_power + detection + CoT)
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=signalsnipe
Group=signalsnipe
ExecStart=/opt/signalsnipe/run-scan.sh
Restart=always
RestartSec=2
Nice=-5
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target

# /etc/systemd/system/signalsnipe-scan.service.d/override.conf
[Service]
Environment=SIGNALSNIPE_CONFIG=/var/lib/signalsnipe/config.json
```

## Config file
```
-rw-r--r-- 1 signalsnipe signalsnipe 1767 Jan 29 17:05 /var/lib/signalsnipe/config.json
```

