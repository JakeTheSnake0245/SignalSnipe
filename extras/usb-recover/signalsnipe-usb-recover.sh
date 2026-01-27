#!/usr/bin/env bash
set -euo pipefail

UNIT="signalsnipe-scan.service"

# Only consider recovery if these show up recently (exclude "Detached kernel driver" on purpose)
LOOKBACK="5 minutes ago"
PATTERN="usb_claim_interface error|Failed to open rtlsdr device|No supported devices found|No devices found"

LOCKFILE="/run/lock/signalsnipe-usb_recover.lock"
LASTFILE="/run/signalsnipe-usb_recover.last"
COOLDOWN_SEC=300

log() { echo "[signalsnipe-usb-recover] $*" | systemd-cat -t signalsnipe-usb-recover -p warning; }
err() { echo "[signalsnipe-usb-recover] $*" | systemd-cat -t signalsnipe-usb-recover -p err; }

recent_error() {
  journalctl -u "${UNIT}" --since "${LOOKBACK}" --no-pager 2>/dev/null | grep -Eiq "${PATTERN}"
}

service_state() {
  systemctl is-active "${UNIT}" 2>/dev/null || echo "unknown"
}

cooldown_ok() {
  local now last
  now="$(date +%s)"
  if [[ -f "${LASTFILE}" ]]; then
    last="$(cat "${LASTFILE}" 2>/dev/null || echo 0)"
    if [[ "${last}" =~ ^[0-9]+$ ]] && (( now - last < COOLDOWN_SEC )); then
      return 1
    fi
  fi
  return 0
}

mark_cooldown() {
  date +%s > "${LASTFILE}" 2>/dev/null || true
}

dongle_openable_idle() {
  # Only call this when the scanner is STOPPED (otherwise "busy" is expected)
  timeout 4 rtl_test -t >/dev/null 2>&1
}

find_usb_devname() {
  local d v p prod
  for d in /sys/bus/usb/devices/*; do
    [[ -f "${d}/idVendor" && -f "${d}/idProduct" ]] || continue
    v="$(cat "${d}/idVendor" 2>/dev/null || true)"
    p="$(cat "${d}/idProduct" 2>/dev/null || true)"
    prod="$(cat "${d}/product" 2>/dev/null || true)"

    if [[ "${v}:${p}" == "0bda:2838" ]]; then
      basename "${d}"
      return 0
    fi

    if echo "${prod}" | grep -Eiq 'RTL2832|RTL2838|RTL-SDR|NESDR|Nooelec'; then
      basename "${d}"
      return 0
    fi
  done
  return 1
}

usb_unbind_bind() {
  local dev_name="$1"
  local sys="/sys/bus/usb/drivers/usb"
  if [[ -w "${sys}/unbind" && -w "${sys}/bind" ]]; then
    echo "${dev_name}" > "${sys}/unbind" || true
    sleep 2
    echo "${dev_name}" > "${sys}/bind" || true
    sleep 3
    log "USB unbind/bind issued for ${dev_name}"
    return 0
  fi
  err "No permission to unbind/bind USB (unexpected)"
  return 1
}

kill_rtl_procs() {
  pkill -9 -f "^rtl_power " 2>/dev/null || true
  pkill -9 -f "^rtl_tcp"    2>/dev/null || true
  pkill -9 -f "^rtl_fm"     2>/dev/null || true
  pkill -9 -f "^rtl_sdr"    2>/dev/null || true
  pkill -9 -f "^rtl_test"   2>/dev/null || true
}

main() {
  mkdir -p /run/lock || true

  exec 9>"${LOCKFILE}"
  if ! flock -n 9; then
    exit 0
  fi

  local state
  state="$(service_state)"

  # SAFETY: never touch a healthy running scanner. (Prevents stop/start thrash from stale log matches.)
  if [[ "${state}" == "active" ]]; then
    exit 0
  fi

  # If there's no recent error signature, do nothing.
  if ! recent_error; then
    exit 0
  fi

  if ! cooldown_ok; then
    log "Cooldown active (${COOLDOWN_SEC}s); skipping recovery this tick."
    exit 0
  fi
  mark_cooldown

  log "Recent RTL-SDR error detected; recovering (state=${state})"

  # Stop scanner and kill cgroup
  systemctl stop "${UNIT}" || true
  systemctl kill "${UNIT}" --signal=SIGKILL --kill-who=all 2>/dev/null || true

  # Kill any leftover RTL processes
  kill_rtl_procs
  sleep 1

  # If dongle is already openable while idle now, just restart scanner
  if dongle_openable_idle; then
    log "Dongle openable once idle; restarting scanner (no USB reset needed)."
    systemctl start "${UNIT}" || true
    exit 0
  fi

  # USB reset
  if dev_name="$(find_usb_devname)"; then
    [[ -e "/sys/bus/usb/devices/${dev_name}/power/control" ]] && echo on  > "/sys/bus/usb/devices/${dev_name}/power/control" || true
    [[ -e "/sys/bus/usb/devices/${dev_name}/power/autosuspend" ]] && echo -1 > "/sys/bus/usb/devices/${dev_name}/power/autosuspend" || true
    [[ -e "/sys/bus/usb/devices/${dev_name}/power/autosuspend_delay_ms" ]] && echo -1 > "/sys/bus/usb/devices/${dev_name}/power/autosuspend_delay_ms" || true
    usb_unbind_bind "${dev_name}" || true
  else
    err "Could not find RTL-SDR in /sys/bus/usb/devices (device may be missing)."
    exit 0
  fi

  ok=0
  for _ in $(seq 1 20); do
    if dongle_openable_idle; then
      ok=1
      break
    fi
    sleep 1
  done

  if [[ "${ok}" -ne 1 ]]; then
    err "Recovery did not restore rtl_test open within 20s. Not restarting scanner."
    exit 0
  fi

  log "Dongle recovered (rtl_test OK). Starting scanner."
  systemctl start "${UNIT}" || true
}

main "$@"
