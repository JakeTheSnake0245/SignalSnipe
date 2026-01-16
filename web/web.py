#!/usr/bin/env python3
import json, os
from flask import Flask, request, redirect, url_for, render_template_string


def _dedupe_targets(targets):
    """Deduplicate list of dicts [{'host':..., 'port':...}] preserving order."""
    out = []
    seen = set()
    for t in (targets or []):
        try:
            h = str((t or {}).get("host","")).strip()
            pt = int((t or {}).get("port", 4242))
        except Exception:
            continue
        if not h:
            continue
        k = (h, int(pt))
        if k in seen:
            continue
        seen.add(k)
        out.append({"host": h, "port": int(pt)})
    return out

CONFIG_PATH = os.environ.get("SIGNALSNIPE_CONFIG", "/etc/signalsnipe/config.json")

def load_cfg():
    with open(CONFIG_PATH, "r") as f:
        return json.load(f)

def save_cfg(cfg):
    # Write atomically. If CONFIG_PATH is a symlink (e.g. /etc -> /var/lib),
    # write the tmp file in the *real* directory to avoid permission issues.
    real_path = os.path.realpath(CONFIG_PATH)
    tmp = real_path + ".tmp"
    with open(tmp, "w") as f:
        json.dump(cfg, f, indent=2, sort_keys=True)
    os.replace(tmp, real_path)


def hz_to_mhz_str(hz: int) -> str:
    return f"{(float(hz) / 1e6):.3f}"

def mhz_to_hz(s: str) -> int:
    s = (s or "").strip()
    if not s:
        return 0
    # allow user to type "123.456" or "123.456 MHz"
    s = s.lower().replace("mhz", "").strip()
    try:
        return int(round(float(s) * 1e6))
    except Exception:
        return 0

# Backwards-compatible alias (older code paths)
mhz_str_to_hz = mhz_to_hz


def _clean_ranges(raw_ranges):
    # raw_ranges: list of dicts with keys start_hz/end_hz or start_mhz/end_mhz strings
    cleaned = []
    for r in raw_ranges:
        s = r.get("start_mhz") or r.get("start") or ""
        e = r.get("end_mhz") or r.get("end") or ""
        s = str(s).strip()
        e = str(e).strip()
        if not s or not e:
            continue
        try:
            s_hz = int(round(float(s.lower().replace("mhz","").strip()) * 1e6))
            e_hz = int(round(float(e.lower().replace("mhz","").strip()) * 1e6))
        except Exception:
            continue
        if s_hz <= 0 or e_hz <= 0:
            continue
        if e_hz <= s_hz:
            continue
        cleaned.append({"start_hz": s_hz, "end_hz": e_hz})
    return cleaned

app = Flask(__name__)

TPL = r"""
<!doctype html>
<html>
<head>
  <meta charset="utf-8"/>
  <title>SignalSnipe</title>
  <meta name="viewport" content="width=device-width, initial-scale=1"/>
  <style>
    :root {
      --bg: #0b0f0d;
      --panel: #101814;
      --panel2: #0f1411;
      --border: #1f2a24;
      --text: #e6f3ea;
      --muted: #9fb3a7;
      --accent: #39d98a;
      --accent2: #2aa76c;
      --danger: #ff5c5c;
      --inputbg: #0b120e;
    }
    body {
      margin: 18px;
      font-family: system-ui, -apple-system, Segoe UI, Roboto, sans-serif;
      background: radial-gradient(1200px 600px at 20% 0%, #0f1a14 0%, var(--bg) 40%, #070a08 100%);
      color: var(--text);
    }
    h1 { margin: 0 0 6px 0; font-size: 1.4rem; }
    small { color: var(--muted); }
    .card {
      background: linear-gradient(180deg, var(--panel) 0%, var(--panel2) 100%);
      border: 1px solid var(--border);
      border-radius: 14px;
      padding: 14px;
      margin: 12px 0;
      box-shadow: 0 6px 18px rgba(0,0,0,.35);
    }
    .row { display: grid; grid-template-columns: 1fr 1fr; gap: 14px; }
    label { display: block; font-size: .92rem; color: var(--muted); margin-top: 8px; }
    input, select, textarea {
      width: 100%;
      padding: 10px 10px;
      margin-top: 6px;
      border-radius: 10px;
      border: 1px solid var(--border);
      background: var(--inputbg);
      color: var(--text);
      outline: none;
    }
    input:focus, select:focus, textarea:focus {
      border-color: rgba(57, 217, 138, 0.6);
      box-shadow: 0 0 0 3px rgba(57,217,138,.15);
    }
    .btnbar { display: flex; gap: 10px; flex-wrap: wrap; margin-top: 10px; }
    button {
      padding: 10px 14px;
      border-radius: 12px;
      border: 1px solid var(--border);
      background: rgba(57, 217, 138, 0.14);
      color: var(--text);
      cursor: pointer;
    }
    button:hover { border-color: rgba(57,217,138,.55); }
    .danger { background: rgba(255,92,92,.12); border-color: rgba(255,92,92,.25); }
    .danger:hover { border-color: rgba(255,92,92,.6); }
    .mini { font-size: .85rem; color: var(--muted); }
    .pill {
      display: inline-block;
      padding: 4px 10px;
      border: 1px solid var(--border);
      border-radius: 999px;
      color: var(--muted);
      background: rgba(255,255,255,.04);
      font-size: .82rem;
    }

    /* Range rows */
    .range-grid {
      display: grid;
      grid-template-columns: 1fr 1fr 1.2fr auto;
      gap: 10px;
      align-items: end;
      margin-top: 10px;
    }
    .range-row {
      border: 1px solid var(--border);
      border-radius: 14px;
      padding: 12px;
      background: rgba(255,255,255,.03);
      margin-top: 10px;
    }
    .range-row h3 {
      margin: 0 0 6px 0;
      font-size: .95rem;
      color: var(--accent);
      font-weight: 600;
    }
    .mhz-suffix {
      position: relative;
    }
    .mhz-suffix input {
      padding-right: 54px;
    }
    .mhz-suffix::after {
      content: "MHz";
      position: absolute;
      right: 14px;
      top: 44px;
      color: var(--muted);
      font-size: .9rem;
      pointer-events: none;
    }
    @media (max-width: 920px) {
      .range-grid { grid-template-columns: 1fr; }
    }
  
/* --- SignalSnipe mobile fix: prevent overlap in range rows --- */
.rangeRow { display:flex; flex-wrap:wrap; gap:12px; align-items:center; }
.rangeRow .field { flex:1 1 260px; min-width:180px; }
.rangeRow .removeBtn { flex:0 0 auto; }

@media (max-width: 720px) {
  .rangeRow .field { flex:1 1 100%; min-width:0; }
  .rangeRow .removeBtn { width:100%; }
}


/* --- Mobile ranges fix (real classes) --- */
@media (max-width: 720px) {
  .range-grid { grid-template-columns: 1fr !important; }
  .mhz-suffix::after { top: 42px; }
}

</style>
</head>
<body>
  <h1>SignalSnipe</h1>
  <div class="mini">
    <span class="pill">Night UI</span>
    <span class="pill">Manual multi-range</span>
    <span class="pill">ZeroTier friendly</span>
    <div style="margin-top:6px;">Edits apply immediately — scanner reads config every pass.</div>
  </div>

  <form method="post" action="/save" id="cfgForm">

    <div class="card">
      <h2 style="margin:0 0 6px 0;">RF Scan</h2>

      <div class="row">
        <div>
          <label>Integration (seconds)</label>
          <input name="integration_s" value="{{cfg['scan']['integration_s']}}" type="number" min="1" step="1"/>
          <label>Step (Hz)</label>
          <input name="step_hz" value="{{cfg['scan']['step_hz']}}" type="number" min="1000" step="1000"/>
          <label>Threshold (dB)</label>
          <input name="threshold_dbfs" value="{{cfg['scan']['threshold_dbfs']}}" type="number" step="0.5"/>
        </div>

        <div>
          <label>Min Duration (seconds)</label>
          <input name="min_duration_s" value="{{cfg['scan']['min_duration_s']}}" type="number" min="1" step="1"/>
          <label>Cooldown (seconds)</label>
          <input name="cooldown_s" value="{{cfg['scan']['cooldown_s']}}" type="number" min="0" step="1"/>
          <label>PPM</label>
          <input name="ppm" value="{{cfg['device']['ppm']}}" type="number" step="1"/>
        </div>
      </div>

      <div class="row">
        <div>
          <label>Gain Mode</label>
          <select name="gain_mode">
            <option value="manual" {% if cfg['device']['gain_mode']=='manual' %}selected{% endif %}>manual</option>
            <option value="auto" {% if cfg['device']['gain_mode']=='auto' %}selected{% endif %}>auto</option>
          </select>
        </div>
        <div>
          <label>Gain (dB) (manual mode)</label>
          <input name="gain_db" value="{{cfg['device']['gain_db']}}" type="number" step="0.1"/>
        </div>
      </div>
    </div>

    <div class="card">
      <h2 style="margin:0 0 6px 0;">Frequency Ranges</h2>
      <div class="mini">Enter frequencies in <b>MHz</b> (example: <code>433.920</code>). Ranges are stored in config as Hz.</div>

      <div id="rangesContainer">
        {% for r in ranges %}
        <div class="range-row">
          <h3>Range {{loop.index}}</h3>
          <div class="range-grid">
            <div class="mhz-suffix">
              <label>Start</label>
              <input name="range_start_mhz" value="{{r.start_mhz}}" inputmode="decimal" placeholder="e.g. 30.000"/>
            </div>
            <div class="mhz-suffix">
              <label>End</label>
              <input name="range_end_mhz" value="{{r.end_mhz}}" inputmode="decimal" placeholder="e.g. 88.000"/>
            </div>
            <div>
              <label>Label</label>
              <input name="range_label" value="{{r.label}}" placeholder="e.g. VHF Low"/>
            </div>
            <div>
              <label>&nbsp;</label>
              <button type="button" class="danger" onclick="removeRange(this)">Remove</button>
            </div>
          </div>
        </div>
        {% endfor %}
      </div>

      <div class="btnbar">
        <button type="button" onclick="addRange()">Add Range</button>
      </div>

      <div class="mini" style="margin-top:10px;">
        Tip: huge spans + tiny steps are heavy. Start with a few ranges and tune threshold/duration first.
      </div>
    </div>

    <div class="card">
      <h2 style="margin:0 0 6px 0;">Location / Meta</h2>
      <div class="row">
        <div>
          <label>Manual MGRS (optional)</label>
          <input name="mgrs" value="{{cfg['location']['mgrs']}}" />
          <label>Latitude</label>
          <input name="lat" value="{{cfg['location']['lat']}}" type="number" step="0.000001"/>
          <label>Longitude</label>
          <input name="lon" value="{{cfg['location']['lon']}}" type="number" step="0.000001"/>
        </div>
        <div>
          <label>Sensor Name</label>
          <input name="sensor_name" value="{{cfg['meta']['sensor_name']}}" />
          <label>Antenna</label>
          <input name="antenna" value="{{cfg['meta']['antenna']}}" />
          <label>Notes</label>
          <input name="notes" value="{{cfg['meta']['notes']}}" />
        </div>
      </div>
    </div>

    <div class="card">
      <h2 style="margin:0 0 6px 0;">TAK / CoT Output</h2>
      <div class="row">
        <div>
          <label>Enable CoT</label>
          <select name="cot_enabled">
            <option value="true" {% if cfg['cot']['enabled'] %}selected{% endif %}>true</option>
            <option value="false" {% if not cfg['cot']['enabled'] %}selected{% endif %}>false</option>
          </select>
          <label>UDP Host (ATAK ZeroTier IP)</label>
          <input name="udp_host" value="{{cfg['cot']['udp_host']}}" />
        </div>
        <div>
          <label>UDP Port</label>
          <input name="udp_port" value="{{cfg['cot']['udp_port']}}" type="number" step="1"/>
          <label>Callsign</label>
          <input name="callsign" value="{{cfg['cot']['callsign']}}" />
          <div id="cotTargetsWrap" style="margin-top:0.75rem;">
            <div style="font-weight:600; margin-bottom:0.25rem;">Additional CoT Targets</div>
            <div style="font-size:0.85rem; opacity:0.85; margin-bottom:0.5rem;">
              Add extra destinations. The main UDP Host/Port above remains the default.
            </div>

            <div id="cotTargetsList">
              {% for t in cfg.get("cot",{}).get("extra_targets", []) %}
              <div class="row" style="display:flex; gap:0.5rem; align-items:center; margin-bottom:0.35rem;">
                <input name="cot_target_host" value="{{ t.get('host','') }}" placeholder="IP/Host" style="flex:1;" />
                <input name="cot_target_port" value="{{ t.get('port', 4242) }}" type="number" step="1" style="width:8rem;" />
                <button type="button" class="btn" onclick="removeRow(this)">Remove</button>
              </div>
              {% endfor %}
            </div>

            <button type="button" class="btn" onclick="addCotTarget()">Add CoT Target</button>
          </div>

        </div>
      </div>

      <div class="btnbar">
        <button type="submit">Save</button>
        <button formaction="/test" formmethod="post" type="submit" class="danger">Send Test CoT</button>
      </div>
    
    <div class="card">
      <h2 style="margin:0 0 6px 0;">Chat / GeoChat Output</h2>
      <div class="mini">Send RF hit messages as <b>GeoChat</b> to ATAK/Wintak. Leave <b>To UID</b> blank to avoid targeting a single UID.</div>
      <div class="row">
        <div>
          <label>Enable Chat</label>
          <select name="chat_enabled">
            <option value="true" {% if cfg.get('chat',{}).get('enabled', False) %}selected{% endif %}>true</option>
            <option value="false" {% if not cfg.get('chat',{}).get('enabled', False) %}selected{% endif %}>false</option>
          </select>
          <label>Chat UDP Host (TAK/ATAK ZeroTier IP)</label>
          <input name="chat_udp_host" value="{{cfg.get('chat',{}).get('udp_host','')}}" />
          <label>Chat UDP Port</label>
          <input name="chat_udp_port" value="{{cfg.get('chat',{}).get('udp_port',4242)}}" type="number" step="1"/>
        </div>
        <div>
          <label>Chatroom</label>
          <input name="chatroom" value="{{cfg.get('chat',{}).get('chatroom','SignalSnipe')}}" />
          <label>From Callsign</label>
          <input name="from_callsign" value="{{cfg.get('chat',{}).get('from_callsign','SignalSnipe')}}" />
          <div id="chatTargetsWrap" style="margin-top:0.75rem;">
            <div style="font-weight:600; margin-bottom:0.25rem;">Additional Chat Targets</div>
            <div style="font-size:0.85rem; opacity:0.85; margin-bottom:0.5rem;">
              Add extra destinations for GeoChat. The main Chat UDP Host/Port above remains the default.
            </div>

            <div id="chatTargetsList">
              {% for t in cfg.get("chat",{}).get("extra_targets", []) %}
              <div class="row" style="display:flex; gap:0.5rem; align-items:center; margin-bottom:0.35rem;">
                <input name="chat_target_host" value="{{ t.get('host','') }}" placeholder="IP/Host" style="flex:1;" />
                <input name="chat_target_port" value="{{ t.get('port', 4242) }}" type="number" step="1" style="width:8rem;" />
                <button type="button" class="btn" onclick="removeRow(this)">Remove</button>
              </div>
              {% endfor %}
            </div>

            <button type="button" class="btn" onclick="addChatTarget()">Add Chat Target</button>
          </div>

          <label>To UID (optional)</label>
          <input name="to_uid" value="{{cfg.get('chat',{}).get('to_uid','')}}" placeholder="leave blank for non-targeted geochat"/>
        </div>
      </div>
    </div>

  </form>

</script>


<script>
function _ss_removeRow(btn){
  var n = btn;
  while(n && n.className !== "row"){ n = n.parentNode; }
  if(n && n.parentNode){ n.parentNode.removeChild(n); }
}
function addCotTarget(){
  var list = document.getElementById("cotTargetsList");
  if(!list){ return; }
  var div = document.createElement("div");
  div.className = "row";
  div.style.cssText = "display:flex; gap:0.5rem; align-items:center; margin-bottom:0.35rem;";
  div.innerHTML =
    '<input name="cot_target_host" value="" placeholder="IP/Host" style="flex:1;" />' +
    '<input name="cot_target_port" value="4242" type="number" step="1" style="width:8rem;" />' +
    '<button type="button" onclick="_ss_removeRow(this)">Remove</button>';
  list.appendChild(div);
}
function addChatTarget(){
  var list = document.getElementById("chatTargetsList");
  if(!list){ return; }
  var div = document.createElement("div");
  div.className = "row";
  div.style.cssText = "display:flex; gap:0.5rem; align-items:center; margin-bottom:0.35rem;";
  div.innerHTML =
    '<input name="chat_target_host" value="" placeholder="IP/Host" style="flex:1;" />' +
    '<input name="chat_target_port" value="4242" type="number" step="1" style="width:8rem;" />' +
    '<button type="button" onclick="_ss_removeRow(this)">Remove</button>';
  list.appendChild(div);
}
</script>

</body>
</html>
"""

@app.get("/")
def index():
    cfg = load_cfg()
    ranges = []
    for r in cfg.get("scan", {}).get("ranges", []):
        try:
            start_mhz = hz_to_mhz_str(int(r.get("start_hz", 0)))
            end_mhz = hz_to_mhz_str(int(r.get("end_hz", 0)))
        except Exception:
            start_mhz = "0.000"
            end_mhz = "0.000"
        ranges.append({
            "start_mhz": start_mhz,
            "end_mhz": end_mhz,
            "label": r.get("label", "")
        })
    cfg.setdefault("cot", {})
    cfg.setdefault("chat", {})
    # extra targets = cfg targets excluding the default host/port
    try:
        dch = str(cfg["cot"].get("udp_host","")).strip()
        dcp = int(cfg["cot"].get("udp_port",4242) or 4242)
        cot_t = (cfg["cot"].get("targets") or [])
        cfg["cot"]["extra_targets"] = [t for t in cot_t if str((t or {}).get("host","")).strip() != dch or int((t or {}).get("port",dcp) or dcp) != dcp]
    except Exception:
        cfg["cot"]["extra_targets"] = []
    try:
        dh = str(cfg["chat"].get("udp_host") or cfg["cot"].get("udp_host","")).strip()
        dp = int(cfg["chat"].get("udp_port") or cfg["cot"].get("udp_port",4242) or 4242)
        chat_t = (cfg["chat"].get("targets") or [])
        cfg["chat"]["extra_targets"] = [t for t in chat_t if str((t or {}).get("host","")).strip() != dh or int((t or {}).get("port",dp) or dp) != dp]
    except Exception:
        cfg["chat"]["extra_targets"] = []
    return render_template_string(TPL, cfg=cfg, ranges=ranges)

@app.post("/save")
def save():
    cfg = load_cfg()

    # scan params
    cfg["scan"]["integration_s"] = int(request.form["integration_s"])
    cfg["scan"]["step_hz"] = int(request.form["step_hz"])
    cfg["scan"]["threshold_dbfs"] = float(request.form["threshold_dbfs"])
    # Keep scanner + UI compatible: scanner uses min_dur_s, older UI used min_duration_s
    md = int(request.form["min_duration_s"])
    cfg["scan"]["min_dur_s"] = md
    cfg["scan"]["min_duration_s"] = md
    cfg["scan"]["cooldown_s"] = int(request.form["cooldown_s"])

    # device params
    cfg["device"]["ppm"] = int(request.form["ppm"])
    cfg["device"]["gain_mode"] = request.form["gain_mode"]
    cfg["device"]["gain_db"] = float(request.form["gain_db"])

    # location/meta
    cfg["location"]["mgrs"] = request.form["mgrs"]
    cfg["location"]["lat"] = float(request.form["lat"])
    cfg["location"]["lon"] = float(request.form["lon"])
    cfg["meta"]["sensor_name"] = request.form["sensor_name"]
    cfg["meta"]["antenna"] = request.form["antenna"]
    cfg["meta"]["notes"] = request.form["notes"]

    # cot output
    cfg["cot"]["enabled"] = (request.form["cot_enabled"].lower() == "true")
    cfg["cot"]["udp_host"] = request.form["udp_host"]
    cfg["cot"]["udp_port"] = int(request.form["udp_port"])
    cfg["cot"]["callsign"] = request.form["callsign"]
    # --- Chat defaults (broadcast) ---
    cfg.setdefault("chat", {})

    # If UI exposes chat fields, honor them.
    chat_host = (request.form.get("chat_udp_host", "") or "").strip()
    chat_port = (request.form.get("chat_udp_port", "") or "").strip()

    if chat_host:
        cfg["chat"]["udp_host"] = chat_host
    elif not str(cfg["chat"].get("udp_host","")).strip():
        cfg["chat"]["udp_host"] = (cfg.get("cot", {}).get("udp_host", "") or "").strip()

    if chat_port:
        cfg["chat"]["udp_port"] = int(chat_port)
    elif not str(cfg["chat"].get("udp_port","")).strip():
        cfg["chat"]["udp_port"] = int(cfg.get("cot", {}).get("udp_port", 4242) or 4242)

    # Honor UI fields (do not silently override)
    cfg["chat"]["enabled"] = (request.form.get("chat_enabled", "false").lower() == "true")
    cfg["chat"]["chatroom"] = (request.form.get("chatroom", "SignalSnipe") or "SignalSnipe").strip()
    cfg["chat"]["from_callsign"] = (request.form.get("from_callsign", cfg.get("cot", {}).get("callsign", "SignalSnipe")) or "SignalSnipe").strip()
    cfg["chat"]["to_uid"] = (request.form.get("to_uid", "") or "").strip()  # blank = broadcast


    # ranges (boxes)
    starts = request.form.getlist("range_start_mhz")
    ends = request.form.getlist("range_end_mhz")
    labels = request.form.getlist("range_label")

    new_ranges = []
    for i in range(max(len(starts), len(ends), len(labels))):
        s = starts[i] if i < len(starts) else ""
        e = ends[i] if i < len(ends) else ""
        lab = labels[i] if i < len(labels) else ""
        s_hz = mhz_str_to_hz(s)
        e_hz = mhz_str_to_hz(e)
        if s_hz > 0 and e_hz > 0 and e_hz > s_hz:
            new_ranges.append({
                "start_hz": int(s_hz),
                "end_hz": int(e_hz),
                "label": lab.strip() or f"{s_hz}-{e_hz}"
            })

    cfg["scan"]["ranges"] = new_ranges
    # Build CoT/Chat targets from UI rows (default + extras), run LAST so it persists
    try:
        # ---- CoT ----
        dhost = str(cfg.get("cot",{}).get("udp_host","")).strip()
        dport = int(cfg.get("cot",{}).get("udp_port",4242) or 4242)
        hosts = request.form.getlist("cot_target_host")
        ports = request.form.getlist("cot_target_port")
        extras = []
        for i in range(min(len(hosts), len(ports))):
            h = str(hosts[i]).strip()
            if not h:
                continue
            try:
                pt = int(str(ports[i]).strip() or dport)
            except Exception:
                pt = dport
            extras.append({"host": h, "port": int(pt)})
        targets = ([{"host": dhost, "port": int(dport)}] if dhost else []) + extras
        cfg.setdefault("cot", {})
        cfg["cot"]["targets"] = _dedupe_targets(targets)
    
        # ---- Chat ----
        dhost = str(cfg.get("chat",{}).get("udp_host") or cfg.get("cot",{}).get("udp_host","")).strip()
        dport = int(cfg.get("chat",{}).get("udp_port") or cfg.get("cot",{}).get("udp_port",4242) or 4242)
        hosts = request.form.getlist("chat_target_host")
        ports = request.form.getlist("chat_target_port")
        extras = []
        for i in range(min(len(hosts), len(ports))):
            h = str(hosts[i]).strip()
            if not h:
                continue
            try:
                pt = int(str(ports[i]).strip() or dport)
            except Exception:
                pt = dport
            extras.append({"host": h, "port": int(pt)})
        targets = ([{"host": dhost, "port": int(dport)}] if dhost else []) + extras
        cfg.setdefault("chat", {})
        cfg["chat"]["targets"] = _dedupe_targets(targets)
    except Exception:
        pass
    save_cfg(cfg)
    return redirect(url_for("index"))

@app.post("/test")
def test():
    # Leave test behavior as-is (scanner handles real alerts)
    cfg = load_cfg()
    import socket, uuid
    from datetime import datetime, timezone

    now = datetime.now(timezone.utc)
    t = now.strftime("%Y-%m-%dT%H:%M:%SZ")
    stale = (now.timestamp() + 120)
    stale_t = datetime.fromtimestamp(stale, tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    sensor_name = (cfg.get("meta",{}).get("sensor_name","SignalSnipe") or "SignalSnipe").strip()
    uid_prefix = cfg.get("cot",{}).get("uid_prefix","SIGNALSNIPE")
    uid = f"{uid_prefix}-SENSOR-{sensor_name}"
    lat = float(cfg["location"].get("lat", 35.0))
    lon = float(cfg["location"].get("lon", -78.0))
    callsign = cfg["cot"].get("callsign", "RF-SENSOR")
    msg = f"TEST CoT from {cfg['meta'].get('sensor_name','SignalSnipe')}"
    xml = (f'<event version="2.0" uid="{uid}" type="{cfg.get("cot",{}).get("sensor_type","a-f-G-E-S-E")}" how="m-g" '
           f'time="{t}" start="{t}" stale="{stale_t}">'
           f'<point lat="{lat}" lon="{lon}" hae="9999999" ce="9999999" le="9999999"/>'
           f'<detail><contact callsign="{callsign}"/><remarks>{msg}</remarks></detail></event>').encode()

    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    chat = cfg.get("chat", {}) or {}
    host = str(chat.get("udp_host") or cfg["cot"]["udp_host"]).strip()
    port = int(chat.get("udp_port") or cfg["cot"]["udp_port"])
    s.sendto(xml, (cfg["cot"]["udp_host"], int(cfg["cot"]["udp_port"])))
    s.close()
    return redirect(url_for("index"))

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8088)
