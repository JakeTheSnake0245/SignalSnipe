#!/usr/bin/env python3
import json, os
from datetime import datetime, timezone

DEFAULT_BASELINE_PATH = "/var/lib/signalsnipe/baseline.json"
DEFAULT_STATUS_PATH   = "/var/lib/signalsnipe/baseline_status.json"

def _utc_ts():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

def _ensure_dir(path: str):
    d = os.path.dirname(os.path.abspath(path))
    if d and not os.path.isdir(d):
        os.makedirs(d, exist_ok=True)

def load_json(path: str, default=None):
    try:
        with open(path, "r") as f:
            return json.load(f)
    except Exception:
        return default

def save_json(path: str, obj):
    _ensure_dir(path)
    real_path = os.path.realpath(path)
    tmp = real_path + ".tmp"
    with open(tmp, "w") as f:
        json.dump(obj, f, indent=2, sort_keys=True)
    os.replace(tmp, real_path)

def load_status(path: str = DEFAULT_STATUS_PATH):
    return load_json(path, default={"state": "idle", "ts": _utc_ts()})

def save_status(state: str, msg: str = "", **kv):
    path = kv.pop("status_path", DEFAULT_STATUS_PATH)
    rec = {"state": state, "msg": msg, "ts": _utc_ts()}
    rec.update(kv or {})
    save_json(path, rec)

def load_baseline(path: str = DEFAULT_BASELINE_PATH):
    return load_json(path, default=None)

def save_baseline(obj, path: str = DEFAULT_BASELINE_PATH):
    save_json(path, obj)

def range_key(start_hz: int, end_hz: int, step_hz: int) -> str:
    return f"{int(start_hz)}-{int(end_hz)}-{int(step_hz)}"
