#!/usr/bin/env python3
import json, os, re, subprocess, shutil
from flask import Flask, request, redirect, url_for, render_template_string
import sys
APP_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "app"))
if APP_DIR not in sys.path:
    sys.path.insert(0, APP_DIR)
try:
    from baseline import DEFAULT_BASELINE_PATH, DEFAULT_STATUS_PATH, load_baseline, save_baseline, load_status, save_status
except Exception:
    DEFAULT_BASELINE_PATH = "/var/lib/signalsnipe/baseline.json"
    DEFAULT_STATUS_PATH = "/var/lib/signalsnipe/baseline_status.json"
    def load_baseline(path=DEFAULT_BASELINE_PATH):
        return None
    def save_baseline(obj, path=DEFAULT_BASELINE_PATH):
        return None
    def load_status(path=DEFAULT_STATUS_PATH):
        return {"state":"unknown"}
    def save_status(state, msg="", **kv):
        return None



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

def _run_ok(cmd, timeout=1.2):
    try:
        p = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=timeout, text=True)
        out = (p.stdout or "") + "\n" + (p.stderr or "")
        return (p.returncode == 0), out
    except Exception:
        return False, ""

def detect_sdr_type(current="rtlsdr"):
    """
    Fast-ish detection.
    - If one device present -> return it.
    - If both present -> return current (avoid flipping).
    - If none -> return current.
    """
    has_hackrf = False
    has_rtl = False

    # Prefer native tools if installed
    if shutil.which("hackrf_info"):
        ok, out = _run_ok(["hackrf_info"], timeout=1.2)
        if ok and ("Found HackRF" in out or "hackrf" in out.lower()):
            has_hackrf = True
    else:
        ok, out = _run_ok(["bash","-lc","lsusb | grep -i -E 'hackrf|1d50:6089'"], timeout=1.2)
        if ok and out.strip():
            has_hackrf = True

    if shutil.which("rtl_test"):
        ok, out = _run_ok(["rtl_test","-t"], timeout=1.2)
        # rtl_test prints "Found 1 device(s)" even when it exits nonzero sometimes; treat that as present
        if ("Found 1 device" in out) or ("Found " in out and "device(s)" in out):
            has_rtl = True
    else:
        ok, out = _run_ok(["bash","-lc","lsusb | grep -i -E 'rtl2832|2838|0bda:2838|realtek'"], timeout=1.2)
        if ok and out.strip():
            has_rtl = True

    if has_hackrf and not has_rtl:
        return "hackrf"
    if has_rtl and not has_hackrf:
        return "rtlsdr"
    if has_hackrf and has_rtl:
        return (current or "rtlsdr").lower()
    return (current or "rtlsdr").lower()


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

def _newest_baseline_file():
    # Prefer the newest baseline_*.json in /var/lib/signalsnipe (excluding status)
    try:
        import glob, os
        cands = sorted(
            [x for x in glob.glob("/var/lib/signalsnipe/baseline_*.json") if not x.endswith("baseline_status.json")],
            key=lambda x: os.path.getmtime(x),
            reverse=True
        )
        return cands[0] if cands else None
    except Exception:
        return None

def _resolve_baseline_path(cfg):
    cfg = cfg or {}
    cfg.setdefault("scan", {})
    baseline_path = str(cfg["scan"].get("baseline_path", DEFAULT_BASELINE_PATH) or DEFAULT_BASELINE_PATH).strip() or DEFAULT_BASELINE_PATH
    if os.path.exists(baseline_path):
        return baseline_path
    nb = _newest_baseline_file()
    if nb and os.path.exists(nb):
        return nb
    return baseline_path



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


/* --- Mobile layout improvements --- */
@media (max-width: 720px) {
  body { margin: 10px; }
  .row { grid-template-columns: 1fr !important; }
  /* Stack CoT/Chat target rows (they use inline flex + fixed widths) */
  #cotTargetsList .row, #chatTargetsList .row {
    flex-direction: column !important;
    align-items: stretch !important;
  }
  #cotTargetsList .row input, #chatTargetsList .row input {
    width: 100% !important;
  }
  #cotTargetsList .row button, #chatTargetsList .row button {
    width: 100% !important;
  }
}


/* --- Desktop pro layout --- */
@media (min-width: 721px) {
  body { max-width: 1100px; margin: 18px auto; }
  .card { padding: 16px; }
  .card h2 { font-size: 1.05rem; letter-spacing: .2px; }
  .row { gap: 18px; align-items: start; }
  label { margin-top: 10px; }
  input, select, textarea { font-variant-numeric: tabular-nums; }
  .actionsbar {
    position: sticky;
    top: 12px;
    z-index: 50;
    display: flex;
    gap: 10px;
    flex-wrap: wrap;
    align-items: center;
    padding: 10px 12px;
    margin: 12px 0;
    border: 1px solid var(--border);
    border-radius: 14px;
    background: linear-gradient(180deg, rgba(16,24,20,.96) 0%, rgba(15,20,17,.96) 100%);
    box-shadow: 0 8px 22px rgba(0,0,0,.35);
    backdrop-filter: blur(6px);
  }
  .actionsbar .mini { margin-left: auto; }
}

</style>
</head>
<body>
  <div class="btnbar">
    <a class="navbtn" href="/">Config</a>
    <a class="navbtn" href="/baseline">Baseline Surveys</a>
  </div>

  <h1>SignalSnipe</h1>
  <div class="mini">
    <span class="pill">Night UI</span>
    <span class="pill">Manual multi-range</span>
    <span class="pill">ZeroTier friendly</span>
    <div style="margin-top:6px;">Edits apply immediately — scanner reads config every pass.</div>
  </div>

  <form method="post" action="/save" id="cfgForm">

  <div class="actionsbar">
    <button type="submit">Save</button>
    <button formaction="/test" formmethod="post" type="submit" class="danger">Send Test CoT</button>
    <div class="mini">Desktop quick actions (sticky)</div>
  </div>


    <div class="card">
      <h2 style="margin:0 0 6px 0;">RF Scan</h2>

      <div class="row">
        <div>
          <label>Integration (seconds)</label>
          <input name="integration_s" value="{{cfg['scan']['integration_s']}}" type="number" min="1" step="1"/>
          <label>Step (Hz)</label>
            <select name="step_hz" id="step_hz_select" data-devtype="{{cfg['device'].get('type','rtlsdr')}}">
              <!-- RTL-SDR clean steps -->
              <optgroup label="RTL-SDR (clean)">
                {% for v in [1000,2000,5000,10000,12500,25000,50000,100000,125000,200000,250000,500000,1000000] %}
                <option value="{{v}}" {% if cfg['scan']['step_hz']==v %}selected{% endif %}>{{v}}</option>
                {% endfor %}
              </optgroup>
              <!-- HackRF clean steps -->
              <optgroup label="HackRF (clean)">
                {% for v in [100000,200000,250000,500000,1000000,2000000,5000000] %}
                <option value="{{v}}" {% if cfg['scan']['step_hz']==v %}selected{% endif %}>{{v}}</option>
                {% endfor %}
              </optgroup>
            </select>
          <label>Threshold (dB)</label>
            <input name="threshold_dbfs" id="threshold_dbfs" value="{{cfg['scan']['threshold_dbfs']}}" type="text" inputmode="decimal" placeholder="-17.0"/>
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
                <button type="button" class="btn" onclick="_ss_removeRow(this)">Remove</button>
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
                <button type="button" class="btn" onclick="_ss_removeRow(this)">Remove</button>
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

  // --- Frequency range add/remove (fix broken Add Range button) ---
  function addRange(){
    var c = document.getElementById("rangesContainer");
    if(!c){ return; }
    var idx = c.querySelectorAll(".range-row").length + 1;
    var div = document.createElement("div");
    div.className = "range-row";
    div.innerHTML =
      '<h3>Range ' + idx + '</h3>' +
      '<div class="range-grid">' +
        '<div class="mhz-suffix">' +
          '<label>Start</label>' +
          '<input name="range_start_mhz" value="" inputmode="decimal" placeholder="e.g. 30.000"/>' +
        '</div>' +
        '<div class="mhz-suffix">' +
          '<label>End</label>' +
          '<input name="range_end_mhz" value="" inputmode="decimal" placeholder="e.g. 88.000"/>' +
        '</div>' +
        '<div>' +
          '<label>Label</label>' +
          '<input name="range_label" value="" placeholder="e.g. VHF Low"/>' +
        '</div>' +
        '<div>' +
          '<label>&nbsp;</label>' +
          '<button type="button" class="danger" onclick="removeRange(this)">Remove</button>' +
        '</div>' +
      '</div>';
    c.appendChild(div);
  }

  function removeRange(btn){
    var n = btn;
    while(n && !n.classList.contains("range-row")){ n = n.parentNode; }
    if(n && n.parentNode){ n.parentNode.removeChild(n); }
    // re-number headings
    var rows = document.querySelectorAll("#rangesContainer .range-row h3");
    for(var i=0;i<rows.length;i++){ rows[i].textContent = "Range " + (i+1); }
  }

  // --- Lock threshold leading '-' (prevents deleting minus) ---
  function _lockLeadingMinus(el){
    if(!el) return;
    var v = (el.value || "").trim();
    if(v === "") { el.value = "-"; return; }
    if(v[0] !== "-") v = "-" + v.replace(/^\+/, "");
    // allow only one leading minus
    v = "-" + v.slice(1).replace(/-/g, "");
    // basic cleanup: allow digits, dot, minus
    v = v.replace(/[^0-9\.\-]/g, "");
    // keep leading '-'
    if(v[0] !== "-") v = "-" + v.replace(/-/g, "");
    el.value = v;
  }

  // --- Step dropdown: prefer device-appropriate options (hide irrelevant optgroup) ---
  function _applyStepOptions(){
    var sel = document.getElementById("step_hz_select");
    if(!sel) return;
    var dev = (sel.getAttribute("data-devtype") || "rtlsdr").toLowerCase();
    var groups = sel.getElementsByTagName("optgroup");
    for(var i=0;i<groups.length;i++){
      var label = (groups[i].getAttribute("label") || "").toLowerCase();
      if(dev.indexOf("hackrf") >= 0){
        groups[i].disabled = label.indexOf("rtl-sdr") >= 0;
        groups[i].style.display = (label.indexOf("rtl-sdr") >= 0) ? "none" : "";
      } else {
        groups[i].disabled = label.indexOf("hackrf") >= 0;
        groups[i].style.display = (label.indexOf("hackrf") >= 0) ? "none" : "";
      }
    }
  }

  // init on load
  window.addEventListener("DOMContentLoaded", function(){
    _applyStepOptions();
    var thr = document.getElementById("threshold_dbfs");
    if(thr){
      _lockLeadingMinus(thr);
      thr.addEventListener("input", function(){ _lockLeadingMinus(thr); });
      thr.addEventListener("blur", function(){ _lockLeadingMinus(thr); });
      thr.addEventListener("keydown", function(e){
        // Block backspace/delete from removing the lone '-'
        if((e.key === "Backspace" || e.key === "Delete") && (thr.value === "-" || thr.value === "")){
          e.preventDefault();
          thr.value = "-";
        }
      });
    }
  });

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

    # scan params (SAFE: tolerate missing/blank fields so UI can't 400)
    cfg.setdefault("scan", {})
    cfg.setdefault("device", {})
    cfg.setdefault("location", {})
    cfg.setdefault("meta", {})
    cfg.setdefault("cot", {})

    def _get(name, default=None):
        v = request.form.get(name, None)
        if v is None:
            return default
        v = str(v).strip()
        return v if v != "" else default

    def _as_int(name, default=0):
        v = _get(name, None)
        if v is None:
            return int(default)
        try:
            return int(float(v))
        except Exception:
            return int(default)

    def _as_float(name, default=0.0):
        v = _get(name, None)
        if v is None:
            return float(default)
        try:
            return float(v)
        except Exception:
            return float(default)

    cfg["scan"]["integration_s"]  = _as_int("integration_s",  cfg["scan"].get("integration_s", 2))
    cfg["scan"]["step_hz"]        = _as_int("step_hz",        cfg["scan"].get("step_hz", 25000))
    cfg["scan"]["threshold_dbfs"] = _as_float("threshold_dbfs", cfg["scan"].get("threshold_dbfs", -35.0))

    # Keep scanner + UI compatible: scanner uses min_dur_s, older UI used min_duration_s
    md = _as_int("min_duration_s", cfg["scan"].get("min_dur_s", cfg["scan"].get("min_duration_s", 4)))
    cfg["scan"]["min_dur_s"] = md
    cfg["scan"]["min_duration_s"] = md
    cfg["scan"]["cooldown_s"] = _as_int("cooldown_s", cfg["scan"].get("cooldown_s", 30))

    # device params
    cfg["device"]["ppm"] = _as_int("ppm", cfg["device"].get("ppm", 0))
    cfg["device"]["gain_mode"] = (_get("gain_mode", cfg["device"].get("gain_mode", "manual")) or "manual").strip()
    cfg["device"]["gain_db"] = _as_float("gain_db", cfg["device"].get("gain_db", 20.7))

    # location/meta
    cfg["location"]["mgrs"] = _get("mgrs", cfg["location"].get("mgrs", "")) or ""
    cfg["location"]["lat"]  = _as_float("lat", cfg["location"].get("lat", 0.0))
    cfg["location"]["lon"]  = _as_float("lon", cfg["location"].get("lon", 0.0))
    cfg["meta"]["sensor_name"] = _get("sensor_name", cfg["meta"].get("sensor_name", "SignalSnipe")) or "SignalSnipe"
    cfg["meta"]["antenna"] = _get("antenna", cfg["meta"].get("antenna", "")) or ""
    cfg["meta"]["notes"]   = _get("notes", cfg["meta"].get("notes", "")) or ""

    # cot output
    ce = (_get("cot_enabled", str(bool(cfg["cot"].get("enabled", False))).lower()) or "false").lower()
    cfg["cot"]["enabled"] = (ce == "true")
    cfg["cot"]["udp_host"] = _get("udp_host", cfg["cot"].get("udp_host", "")) or ""
    cfg["cot"]["udp_port"] = _as_int("udp_port", cfg["cot"].get("udp_port", 4242))
    cfg["cot"]["callsign"] = _get("callsign", cfg["cot"].get("callsign", "RF-SENSOR")) or "RF-SENSOR"


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


BASE_TPL = r"""
<!doctype html>
<html>
<head>
  <meta charset="utf-8"/>
  <title>SignalSnipe - Baseline</title>
  <meta name="viewport" content="width=device-width, initial-scale=1"/>
  <style>
    body { margin: 18px; font-family: system-ui, -apple-system, Segoe UI, Roboto, sans-serif; background: #0b0f0d; color: #e6f3ea; }
    .card { background: #101814; border: 1px solid #1f2a24; border-radius: 14px; padding: 14px; margin: 12px 0; }
    label { display:block; margin-top:10px; color:#9fb3a7; }
    input, select { width:100%; padding:10px; margin-top:6px; border-radius:10px; border:1px solid #1f2a24; background:#0b120e; color:#e6f3ea; }
    .btnbar { display:flex; gap:10px; flex-wrap:wrap; margin-top:10px; }
    button, a.btn { padding:10px 14px; border-radius:12px; border:1px solid #1f2a24; background: rgba(57, 217, 138, 0.14); color:#e6f3ea; cursor:pointer; text-decoration:none; display:inline-block; }
    button:hover, a.btn:hover { border-color: rgba(57,217,138,.55); }
    .danger { background: rgba(255,92,92,.12); border-color: rgba(255,92,92,.25); }
    .danger:hover { border-color: rgba(255,92,92,.6); }
    .pill { display:inline-block; padding:4px 10px; border:1px solid #1f2a24; border-radius:999px; color:#9fb3a7; background: rgba(255,255,255,.04); font-size:.82rem; }
    pre { white-space: pre-wrap; word-break: break-word; background:#0b120e; border:1px solid #1f2a24; border-radius:12px; padding:10px; color:#9fb3a7; }
  </style>
</head>
<body>
  <div class="btnbar">
    <a class="btn" href="/">← Back to Config</a>
    <a class="btn" href="/baseline">Refresh</a>
    <a class="btn" href="/baseline/download">Download Baseline</a>
      <a class="btn" href="/baseline/download_bins_csv">Download Bins CSV</a>
    <a class="btn" href="/baseline/download_csv">Download CSV</a>
  </div>

  <div class="card">
    <h2 style="margin:0 0 8px 0;">Baseline Status</h2>
    <div class="pill">state={{ status.get('state','unknown') }}</div>
    <div class="pill">ts={{ status.get('ts','') }}</div>
    {% if status.get('msg') %}<div style="margin-top:8px;color:#9fb3a7;">{{ status.get('msg') }}</div>{% endif %}
    <pre>{{ status | tojson(indent=2) }}</pre>
  </div>

  <div class="card">
    <h2 style="margin:0 0 8px 0;">Detection Mode</h2>
    <form method="post" action="/baseline/mode">
      <label>Mode</label>
      <select name="detect_mode">
        <option value="threshold" {% if (cfg.get('scan',{}).get('detect_mode','threshold')=='threshold') %}selected{% endif %}>threshold (classic)</option>
        <option value="baseline" {% if (cfg.get('scan',{}).get('detect_mode','threshold')=='baseline') %}selected{% endif %}>baseline (delta over noise floor)</option>
      </select>
      <label>Baseline Delta Threshold (dB)</label>
      <input name="baseline_delta_db" type="number" step="0.1" value="{{ cfg.get('scan',{}).get('baseline_delta_db', 6.0) }}">
      <label>Baseline File Path</label>
      <input name="baseline_path" type="text" value="{{ cfg.get('scan',{}).get('baseline_path', baseline_path) }}">
      <div class="btnbar">
        <button type="submit">Save Mode</button>
      </div>
    </form>
  </div>

  <div class="card">
    <h2 style="margin:0 0 8px 0;">Run Baseline Capture</h2>
    <p style="color:#9fb3a7;margin:0 0 8px 0;">
      This sets a flag in config; the <b>scanner</b> performs capture (so it can safely use the RTL-SDR without conflicts).
    </p>
    <form method="post" action="/baseline/start">
      <label>Capture Duration (seconds)</label>
      <input name="baseline_capture_s" type="number" step="1" value="{{ cfg.get('scan',{}).get('baseline_capture_s', 60) }}">
      <label>Baseline File Path</label>
      <input name="baseline_path" type="text" value="{{ cfg.get('scan',{}).get('baseline_path', baseline_path) }}">
      <div class="btnbar">
        <button type="submit">Start Capture</button>
      </div>
    </form>
  </div>

  <div class="card">
    <h2 style="margin:0 0 8px 0;">Manage Baseline File</h2>

    <form method="post" action="/baseline/clear">
      <div class="btnbar">
        <button class="danger" type="submit">Clear Baseline</button>
      </div>
    </form>

    <form method="post" action="/baseline/upload" enctype="multipart/form-data">
      <label>Upload baseline.json</label>
      <input name="file" type="file" accept=".json,application/json">
      <div class="btnbar">
        <button type="submit">Upload</button>
      </div>
    </form>

    {% if info %}
      <h3 style="margin-top:14px;">Current Baseline Info</h3>
      <pre>{{ info | tojson(indent=2) }}</pre>
    {% else %}
      <p style="color:#9fb3a7;">No baseline file found yet.</p>
    {% endif %}
  </div>

</body>
</html>
"""

def _baseline_info(path):
    try:
        b = load_baseline(path)
        if not b:
            return None
        # keep it lightweight for UI
        info = {
            "created_utc": b.get("created_utc"),
            "scan": b.get("scan"),
            "device": b.get("device"),
            "range_count": len(b.get("ranges") or []),
            "ranges": []
        }
        for rr in (b.get("ranges") or [])[:12]:
            info["ranges"].append({
                "key": rr.get("key"),
                "label": rr.get("label"),
                "start_hz": rr.get("start_hz"),
                "end_hz": rr.get("end_hz"),
                "step_hz": rr.get("step_hz"),
                "n": rr.get("n"),
                "bins": len(rr.get("baseline_bins") or []),
            })
        return info
    except Exception:
        return None

@app.get("/baseline")
def baseline_page():
    cfg = load_cfg()
    cfg.setdefault("scan", {})
    baseline_path = str(cfg["scan"].get("baseline_path", DEFAULT_BASELINE_PATH) or DEFAULT_BASELINE_PATH).strip() or DEFAULT_BASELINE_PATH
    st = load_status(DEFAULT_STATUS_PATH) or {"state":"unknown"}
    info = _baseline_info(baseline_path)
    return render_template_string(BASE_TPL, cfg=cfg, status=st, info=info, baseline_path=baseline_path)

@app.get("/baseline/status")
def baseline_status():
    st = load_status(DEFAULT_STATUS_PATH) or {"state":"unknown"}
    return (st, 200)

@app.post("/baseline/mode")
def baseline_mode():
    cfg = load_cfg()
    cfg.setdefault("scan", {})
    dm = (request.form.get("detect_mode","threshold") or "threshold").strip().lower()
    if dm not in ("threshold","baseline"):
        dm = "threshold"
    cfg["scan"]["detect_mode"] = dm
    try:
        cfg["scan"]["baseline_delta_db"] = float(request.form.get("baseline_delta_db","6.0") or 6.0)
    except Exception:
        cfg["scan"]["baseline_delta_db"] = float(cfg["scan"].get("baseline_delta_db", 6.0) or 6.0)
    bp = (request.form.get("baseline_path","") or "").strip()
    if bp:
        cfg["scan"]["baseline_path"] = bp
    save_cfg(cfg)
    return redirect(url_for("baseline_page"))

@app.post("/baseline/start")
def baseline_start():
    cfg = load_cfg()
    cfg.setdefault("scan", {})
    try:
        cap_s = int(float(request.form.get("baseline_capture_s","60") or 60))
    except Exception:
        cap_s = int(cfg["scan"].get("baseline_capture_s", 60) or 60)
    cap_s = max(10, min(cap_s, 3600))
    cfg["scan"]["baseline_capture_s"] = cap_s
    bp = (request.form.get("baseline_path","") or "").strip()
    if bp:
        cfg["scan"]["baseline_path"] = bp
    cfg["scan"]["baseline_capture"] = True
    save_cfg(cfg)
    try:
        save_status("queued", "Baseline capture queued (scanner will execute)", status_path=DEFAULT_STATUS_PATH, seconds=cap_s)
    except Exception:
        pass
    return redirect(url_for("baseline_page"))

@app.get("/baseline/download")
def baseline_download():
    cfg = load_cfg()
    cfg.setdefault("scan", {})
    baseline_path = _resolve_baseline_path(cfg)
    # If missing, still return to page
    if not os.path.exists(baseline_path):
        return redirect(url_for("baseline_page"))
    # Minimal download without send_file dependency
    data = open(baseline_path, "rb").read()
    return (data, 200, {
        "Content-Type": "application/json",
        "Cache-Control": "no-store, no-cache, must-revalidate, max-age=0",
          "Pragma": "no-cache",
          "Expires": "0",
          "Content-Disposition": "attachment; filename=baseline.json"
    })


@app.get("/baseline/download_csv")
def baseline_download_csv():
    cfg = load_cfg()
    cfg.setdefault("scan", {})
    baseline_path = _resolve_baseline_path(cfg)
    if not os.path.exists(baseline_path):
        return redirect(url_for("baseline_page"))

    # Build a range-summary CSV from the baseline JSON
    import json, io, csv
    b = json.loads(open(baseline_path, "rb").read().decode("utf-8", errors="strict"))

    created = b.get("created_utc","")
    dev = b.get("device") or {}
    scan = b.get("scan") or {}
    ranges = b.get("ranges") or []

    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow([
        "created_utc",
        "ppm","gain_mode","gain_db",
        "scan_step_hz","scan_integration_s",
        "range_key","label","start_hz","end_hz","step_hz","n_bins","n_avg",
        "min_db","max_db","mean_db"
    ])

    for rr in ranges:
        bins = rr.get("baseline_bins") or []
        if bins:
            mn = min(bins); mx = max(bins); mu = (sum(bins)/len(bins))
        else:
            mn = mx = mu = ""
        w.writerow([
            created,
            dev.get("ppm",""), dev.get("gain_mode",""), dev.get("gain_db",""),
            scan.get("step_hz",""), scan.get("integration_s",""),
            rr.get("key",""), rr.get("label",""),
            rr.get("start_hz",""), rr.get("end_hz",""), rr.get("step_hz",""),
            len(bins), rr.get("n",""),
            mn, mx, mu
        ])

    data = buf.getvalue().encode("utf-8")
    return (data, 200, {
        "Content-Type": "text/csv; charset=utf-8",
        "Cache-Control": "no-store, no-cache, must-revalidate, max-age=0",
          "Pragma": "no-cache",
          "Expires": "0",
          "Content-Disposition": "attachment; filename=baseline_ranges.csv"
    })

@app.post("/baseline/upload")
def baseline_upload():
    cfg = load_cfg()
    cfg.setdefault("scan", {})
    baseline_path = str(cfg["scan"].get("baseline_path", DEFAULT_BASELINE_PATH) or DEFAULT_BASELINE_PATH).strip() or DEFAULT_BASELINE_PATH
    f = request.files.get("file")
    if f:
        data = f.read()
        try:
            # validate JSON
            import json
            obj = json.loads(data.decode("utf-8", errors="strict"))
            save_baseline(obj, path=baseline_path)
            save_status("done", "Baseline uploaded", status_path=DEFAULT_STATUS_PATH, baseline_path=baseline_path)
        except Exception as e:
            try:
                save_status("error", f"Upload failed: {e}", status_path=DEFAULT_STATUS_PATH)
            except Exception:
                pass
    return redirect(url_for("baseline_page"))


@app.get("/baseline/download_bins_csv")
def baseline_download_bins_csv():
    cfg = load_cfg()
    cfg.setdefault("scan", {})
    baseline_path = _resolve_baseline_path(cfg)
    if not os.path.exists(baseline_path):
        return redirect(url_for("baseline_page"))

    # delta used to compute per-bin threshold in baseline mode
    try:
        delta = float(cfg.get("scan", {}).get("baseline_delta_db", 6.0) or 6.0)
    except Exception:
        delta = 6.0

    import json, io, csv
    b = json.loads(open(baseline_path, "rb").read().decode("utf-8", errors="strict"))

    created = b.get("created_utc","")
    ranges = b.get("ranges") or []

    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow([
        "created_utc",
        "range_key","label",
        "start_hz","step_hz",
        "bin_index","freq_hz","freq_mhz",
        "baseline_db","baseline_delta_db","threshold_db"
    ])

    for rr in ranges:
        start = int(rr.get("start_hz", 0) or 0)
        step  = int(rr.get("step_hz", 0) or 0)
        key   = rr.get("key", "")
        label = rr.get("label", "")
        bins  = rr.get("baseline_bins") or []
        for i, val in enumerate(bins):
            try:
                baseline = float(val)
            except Exception:
                continue
            fhz = start + i * step
            w.writerow([created, key, label, start, step, i, fhz, fhz/1e6, baseline, delta, baseline + delta])

    data = buf.getvalue().encode("utf-8")
    return (data, 200, {
        "Content-Type": "text/csv; charset=utf-8",
        "Cache-Control": "no-store, no-cache, must-revalidate, max-age=0",
          "Pragma": "no-cache",
          "Expires": "0",
          "Content-Disposition": "attachment; filename=baseline_bins_with_threshold.csv"
    })

@app.post("/baseline/clear")
def baseline_clear():
    cfg = load_cfg()
    cfg.setdefault("scan", {})
    baseline_path = str(cfg["scan"].get("baseline_path", DEFAULT_BASELINE_PATH) or DEFAULT_BASELINE_PATH).strip() or DEFAULT_BASELINE_PATH
    try:
        if os.path.exists(baseline_path):
            os.remove(baseline_path)
    except Exception:
        pass
    try:
        save_status("idle", "Baseline cleared", status_path=DEFAULT_STATUS_PATH)
    except Exception:
        pass
    return redirect(url_for("baseline_page"))


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8088)
