#!/usr/bin/env python3
import json, os, time, uuid, socket, subprocess
import re
try:
    import mgrs
except Exception:
    mgrs = None

import time
from datetime import datetime, timezone
import socket
import uuid

CONFIG_PATH = os.environ.get("SIGNALSNIPE_CONFIG", "/etc/signalsnipe/config.json")
LOG_PATH = os.environ.get("SIGNALSNIPE_LOG", "/var/log/signalsnipe/signalsnipe.log")

def log(msg: str):
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    line = f"{ts} {msg}"
    print(line, flush=True)
    try:
        with open(LOG_PATH, "a") as f:
            f.write(line + "\n")
    except Exception:
        pass

def load_cfg():
    with open(CONFIG_PATH, "r") as f:
        return json.load(f)

def cot_xml(cfg, text: str):
    # Minimal CoT that ATAK/WINTAK will render as a marker
    now = datetime.now(timezone.utc)
    t = now.strftime("%Y-%m-%dT%H:%M:%SZ")
    stale = (now.timestamp() + 120)
    stale_t = datetime.fromtimestamp(stale, tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    uid_prefix = cfg.get('cot',{}).get('uid_prefix','SIGNALSNIPE')
    # Stable UID prevents multiple tracks; allow explicit override via cfg.cot.uid
    uid = str(cfg.get('cot',{}).get('uid','')).strip()
    if not uid:
        base = cfg.get('meta',{}).get('sensor_name') or cfg.get('cot',{}).get('callsign','RF-SENSOR')
        base = re.sub(r'[^A-Za-z0-9_.-]+', '-', str(base)).strip('-') or 'SENSOR'
        uid = f"{uid_prefix}-{base}"
    callsign = cfg["cot"].get("callsign", "RF-SENSOR")
    loc = cfg.get('location',{}) or {}
    lat = float(loc.get('lat', 35.0))
    lon = float(loc.get('lon', -78.0))
    # If user provides MGRS and selects manual_mgrs, convert to lat/lon
    if str(loc.get('mode','')).strip() == 'manual_mgrs':
        m_raw = str(loc.get('mgrs','') or '').strip().upper()
        m_norm = ''
        parts = m_raw.split()
        # Prefer token form: '18S TH 50148 022640' (we'll equalize precision)
        if len(parts) >= 4:
            zb, sq = parts[0], parts[1]
            e = ''.join([c for c in parts[2] if c.isdigit()])
            n = ''.join([c for c in parts[3] if c.isdigit()])
            prec = min(len(e), len(n), 5)
            if prec > 0:
                m_norm = '%s%s%s%s' % (zb, sq, e[:prec], n[:prec])
        if not m_norm:
            # Fallback: compact form; strip whitespace
            m_norm = ''.join(m_raw.split())
            # If trailing digits are odd length, drop the last digit
            if len(m_norm) > 5:
                tail = m_norm[5:]
                if len(tail) % 2 == 1:
                    m_norm = m_norm[:-1]
        if m_norm and mgrs is not None:
            try:
                lat2, lon2 = mgrs.MGRS().toLatLon(m_norm)
                lat = float(lat2); lon = float(lon2)
            except Exception as e:
                try:
                    log("[SignalSnipe] MGRS parse failed: '%s' -> '%s' err=%r" % (m_raw, m_norm, e))
                except Exception:
                    pass
    remarks = text.replace("&","&amp;").replace("<","&lt;").replace(">","&gt;")

    return (
        f'<event version="2.0" uid="{uid}" type="a-f-G-U-C" how="m-g" '
        f'time="{t}" start="{t}" stale="{stale_t}">'
        f'<point lat="{lat}" lon="{lon}" hae="9999999" ce="9999999" le="9999999"/>'
        f'<detail><contact callsign="{callsign}"/>'
        f'<remarks>{remarks}</remarks></detail></event>'
    ).encode("utf-8")

def send_cot(cfg, text: str):
    if not cfg.get("cot", {}).get("enabled", True):
        return
    host = cfg["cot"].get("udp_host", "127.0.0.1")
    port = int(cfg["cot"].get("udp_port", 4242))
    payload = cot_xml(cfg, text)
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    s.sendto(payload, (host, port))
    s.close()



def send_geochat_hit(cfg, text: str):
    """
    Send TAK GeoChat CoT (b-t-f) via UDP.
    This is shaped to look like common ATAK/WinTAK GeoChat CoT.
    """
    chat = cfg.get("chat", {}) or {}
    if not chat.get("enabled", False):
        return

    host = str(chat.get("udp_host", "")).strip()
    port = int(chat.get("udp_port", 4242) or 4242)
    if not host:
        return

    room = str(chat.get("chatroom", "SignalSnipe")).strip() or "SignalSnipe"
    from_callsign = str(chat.get("from_callsign", "SignalSnipe")).strip() or "SignalSnipe"
    to_uid = str(chat.get("to_uid", "")).strip()  # optional (directed)

    # Stable sender UID (so chat sender stays consistent)
    uid_prefix = cfg.get('cot',{}).get('uid_prefix','SIGNALSNIPE')
    base = cfg.get('meta',{}).get('sensor_name') or cfg.get('cot',{}).get('callsign','RF-SENSOR')
    base = re.sub(r'[^A-Za-z0-9_.-]+', '-', str(base)).strip('-') or 'SENSOR'
    sender_uid = f"{uid_prefix}-{base}"

    now = datetime.now(timezone.utc)
    t = now.strftime("%Y-%m-%dT%H:%M:%SZ")
    stale = datetime.fromtimestamp(now.timestamp() + 86400, tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    # Event uid in a GeoChat-ish style
    ev_uid = f"GeoChat.{sender_uid}.{room}.{uuid.uuid4()}"
    msg = (text or "").replace("&","&amp;").replace("<","&lt;").replace(">","&gt;")

    # Optional directed message (receiverUid) + marti dest
    rx_attr = f' receiverUid="{to_uid}"' if to_uid else ""
    marti = f'<marti><dest uid="{to_uid}"/></marti>' if to_uid else ""

    # Many clients use lat/lon 0,0 for chat events; location belongs in separate CoT tracks.
    xml = (
        f'<event version="2.0" uid="{ev_uid}" type="b-t-f" time="{t}" start="{t}" stale="{stale}" how="h-g-i-g-o">'
        f'<point lat="0" lon="0" hae="9999999" ce="9999999" le="9999999" />'
        f'<detail>'
        f'<__chat id="{room}" chatroom="{room}" senderCallsign="{from_callsign}" groupOwner="false"{rx_attr}>'
        f'</__chat>'
        f'<link uid="{sender_uid}" type="a-f-G-U-C-I" relation="p-p" />'
        f'<remarks source="BAO.F.{from_callsign}.{sender_uid}" sourceID="{sender_uid}" to="{room}" time="{t}">{msg}</remarks>'
        f'{marti}'
        f'</detail>'
        f'</event>'
    )

    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    s.sendto(xml.encode("utf-8"), (host, port))
    s.close()
def rtl_power_scan(start_hz: int, end_hz: int, step_hz: int, integration_s: int, gain_db: float, ppm: int):
    # rtl_power output lines look like:
    # date, time, start, end, step, samples, p0, p1, p2, ...
    cmd = [
        "rtl_power",
        "-f", f"{start_hz}:{end_hz}:{step_hz}",
        "-i", str(integration_s),
        "-1",
        "-p", str(ppm),
        "-g", str(gain_db),
        "-"
    ]

    # IMPORTANT:
    # Some rtl_power builds do NOT exit reliably even with -1.
    # If we block here, we never parse, never DETECT, never send.
    # So: enforce a timeout, parse partial stdout if needed.
    timeout_s = max(6, int(integration_s) + 5)

    out_text = ""
    try:
        p = subprocess.run(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            timeout=timeout_s
        )
        out_text = p.stdout or ""
        rc = p.returncode
    except subprocess.TimeoutExpired as ex:
        # subprocess.run() kills the process on timeout; we still can parse what it printed.
        out_text = (ex.stdout or "") if isinstance(ex.stdout, str) else (ex.stdout.decode("utf-8","ignore") if ex.stdout else "")
        rc = 124

    out = (out_text.strip().splitlines() if out_text else [])

    # Find last CSV-like line
    csv_line = None
    for line in reversed(out):
        if "," in line and line.count(",") > 6:
            csv_line = line
            break

    if not csv_line:
        # Surface something useful for logs
        tail = "\n".join(out[-8:]) if out else "(no output)"
        raise RuntimeError(f"rtl_power produced no CSV output (rc={rc}) tail:\n{tail}")

    parts = [x.strip() for x in csv_line.split(",")]
    start = float(parts[2]); end = float(parts[3]); step = float(parts[4])
    bins = [float(x) for x in parts[6:]]
    return start, end, step, bins
def detect_peak(bins, threshold_dbfs):
    # bins are power values from rtl_power (typically dBFS-ish)
    peak = max(bins)
    idx = bins.index(peak)
    return peak, idx, (peak >= threshold_dbfs)

def idx_to_freq(start_hz, step_hz, idx):
    return int(start_hz + step_hz * idx)

def main():
    log("[SignalSnipe] starting")
    last_alert = {}  # key -> last_time
    consecutive = {} # key -> seconds above threshold

    # Heartbeat init (persistent across iterations)
    heartbeat_s = 60
    next_hb = 0.0

    while True:
        try:
            cfg = load_cfg()

            # --- Heartbeat tick (ONE sensor track) ---
            heartbeat_s = int(cfg.get('cot',{}).get('heartbeat_s', 60) or 60)
            now_ts = time.time()
            if now_ts >= next_hb:
                try:
                    nm = cfg.get('meta',{}).get('sensor_name','SignalSnipe')
                    send_cot(cfg, 'SENSOR %s online' % nm)
                except Exception:
                    pass
                next_hb = now_ts + heartbeat_s

            # --- Pull scan + device config ---
            scan = cfg.get("scan", {}) or {}
            dev  = cfg.get("device", {}) or {}

            step_hz       = int(scan.get("step_hz", 25000))
            integration_s = int(scan.get("integration_s", 2))
            threshold     = float(scan.get("threshold_dbfs", scan.get("threshold", -35)))
            min_dur       = int(scan.get("min_dur_s", 4))
            cooldown      = int(scan.get("cooldown_s", 30))

            ppm = int(dev.get("ppm", 0) or 0)
            gain_mode = dev.get("gain_mode", "manual")
            gain_db = float(dev.get("gain_db", 20.7)) if gain_mode == "manual" else 0.0

            ranges = scan.get("ranges", []) or []
            if not ranges:
                log("[SignalSnipe] no ranges configured; sleeping")
                time.sleep(2)
                continue

            for r in ranges:
                start_hz = int(r["start_hz"]); end_hz = int(r["end_hz"])
                label = r.get("label", f"{start_hz}-{end_hz}")

                # run one sweep for this range
                s_hz, e_hz, st_hz, bins = rtl_power_scan(
                    start_hz, end_hz, step_hz, integration_s, gain_db, ppm
                )
                peak, idx, over = detect_peak(bins, threshold)
                peak_hz = idx_to_freq(s_hz, st_hz, idx)

                key = f"{label}:{peak_hz}"
                now = time.time()

                if over:
                    consecutive[key] = consecutive.get(key, 0) + integration_s
                else:
                    consecutive[key] = 0

                # fire alert if above threshold long enough AND cooldown elapsed
                if consecutive[key] >= min_dur:
                    last = last_alert.get(key, 0)
                    if now - last >= cooldown:
                        msg = (f"DETECT {label} peak={peak:.1f} dB "
                               f"freq≈{peak_hz/1e6:.6f} MHz dur={consecutive[key]}s "
                               f"thr={threshold} step={step_hz} gain={gain_db}")
                        try:
                            send_geochat_hit(cfg, msg)
                            log(f"[SignalSnipe] CHAT sent -> {cfg.get('chat',{}).get('udp_host') or cfg.get('cot',{}).get('udp_host')}:{cfg.get('chat',{}).get('udp_port') or cfg.get('cot',{}).get('udp_port')} room={cfg.get('chat',{}).get('chatroom','SignalSnipe')} target={'broadcast' if not cfg.get('chat',{}).get('to_uid') else cfg.get('chat',{}).get('to_uid')}")
                        except Exception as e:
                            log(f"[SignalSnipe] CHAT error: {e}")
                        log(msg)
                        last_alert[key] = now
                        consecutive[key] = 0

        except Exception as e:
            log(f"[SignalSnipe] ERROR: {e}")
            time.sleep(2)

if __name__ == "__main__":
    main()
