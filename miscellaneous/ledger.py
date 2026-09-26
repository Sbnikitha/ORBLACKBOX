"""Tamper-proof log. Each entry includes the hash of the one before it."""
import hashlib
import json
import os
import threading
import time

import config

LOG = os.path.join(config.STATE_DIR, "ledger.jsonl")
_thread_lock = threading.Lock()


def _hash(entry):
    return hashlib.sha256(json.dumps(entry, sort_keys=True).encode()).hexdigest()


def record(entry, path=None):
    """Append one entry chained to the previous hash."""
    path = path or LOG
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with _thread_lock:
        lines = []
        if os.path.exists(path):
            with open(path, encoding="utf-8") as handle:
                lines = [ln for ln in handle.read().splitlines() if ln.strip()]
        prev = json.loads(lines[-1])["hash"] if lines else "GENESIS"
        body = {"time": round(time.time(), 3), **entry, "prev": prev}
        body["hash"] = _hash(body)
        with open(path, "a", encoding="utf-8") as handle:
            handle.write(json.dumps(body) + "\n")
        return body


def read_all(path=None):
    path = path or LOG
    if not os.path.exists(path):
        return []
    out = []
    with open(path, encoding="utf-8") as handle:
        for line in handle:
            try:
                out.append(json.loads(line))
            except json.JSONDecodeError:
                pass
    return out


def verify(path=None):
    """Return None if the log is untouched, otherwise the first bad entry number."""
    path = path or LOG
    if not os.path.exists(path):
        return None
    prev = "GENESIS"
    with open(path, encoding="utf-8") as handle:
        for i, line in enumerate(handle, 1):
            if not line.strip():
                continue
            try:
                raw = json.loads(line)
                stored = raw.pop("hash")
            except (json.JSONDecodeError, KeyError):
                return i
            if raw.get("prev") != prev or _hash(raw) != stored:
                return i
            prev = stored
    return None


def reset(path=None):
    path = path or LOG
    if os.path.exists(path):
        os.remove(path)


def tamper(path=None):
    """Break the chain on purpose so the dashboard can show detection."""
    path = path or LOG
    while len(read_all(path)) < 3:
        record({"type": "status", "or": 1, "status": "SAFE", "alerts": ["seed"]}, path)
    with _thread_lock:
        with open(path, encoding="utf-8") as handle:
            lines = [ln for ln in handle.read().splitlines() if ln.strip()]
        index = 2 if len(lines) >= 3 else len(lines) - 1
        obj = json.loads(lines[index])
        obj["status"] = "FORGED"
        obj["alerts"] = ["forged in the live demo"]
        lines[index] = json.dumps(obj)
        with open(path, "w", encoding="utf-8") as handle:
            handle.write("\n".join(lines) + "\n")
    return verify(path)
