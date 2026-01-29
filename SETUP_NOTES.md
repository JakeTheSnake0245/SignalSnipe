# SignalSnipe v2.0 — Setup Notes (Generated on Pi)

## Timestamp
```
2026-01-29T18:29:51
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
build-essential 12.9ubuntu3
curl 7.81.0-1ubuntu1.21
g++ 4:11.2.0-1ubuntu1
gcc 4:11.2.0-1ubuntu1
git 1:2.34.1-1ubuntu1.15
make 4.3-4.1build1
network-manager 1.36.6-0ubuntu2.2
python3 3.10.6-1~22.04.1
python3-pip 22.0.2+dfsg-1ubuntu0.7
python3-venv 3.10.6-1~22.04.1
rsync 3.2.7-0ubuntu0.22.04.4
rtl-sdr 0.6.0-4
usbutils 1:014-1build1
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
(unable to list or none found)
```

### signalsnipe-web.service
```
(empty/unavailable)
```

### signalsnipe-scan.service
```
(empty/unavailable)
```

## Config file
```
-rw-r--r-- 1 signalsnipe signalsnipe 1767 Jan 29 17:05 /var/lib/signalsnipe/config.json
```
