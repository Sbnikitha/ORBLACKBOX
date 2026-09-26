"""Replay several operating rooms at once. Rules decide the status; models read and explain."""
import math
import argparse
import glob
import json
import os
import random
import threading
import time
from pathlib import Path

import agents
import cases
import config
import fusion
import ledger
import photos
import vision


def photo_with(count):
    photos.ensure()
    hits = []
    for path in glob.glob(os.path.join(config.PHOTO_DIR, "*")):
        if not path.lower().endswith((".jpg", ".jpeg", ".png")):
            continue
        try:
            if int(Path(path).stem.split("_")[0]) == int(count):
                hits.append(path)
        except ValueError:
            continue
    return random.choice(hits) if hits else None


def _look(state, hidden_problem, force_vision):
    """Keep a tray frame for every moment, and flag tools that are still inside."""
    on_tray = max(state["removed"] - (1 if hidden_problem else 0), 0)
    photo = photo_with(on_tray)
    if not photo:
        return
    state["photo"] = os.path.basename(photo)
    try:
        marked = photos.analyze(photo)
        state["vision_count"], _ = vision.count_tray(photo, force=force_vision)
        boxes = []
        inside = state.get("tools_inside") or []
        for box in marked["boxes"]:
            item = dict(box)
            label = (item.get("label") or "").lower()
            if any(name in label for name in inside):
                item["kind"] = "missing"
                item["label"] = f"{item.get('label')} MISSING"
            boxes.append(item)
        state["boxes"] = boxes
        state["frame_w"] = marked["width"]
        state["frame_h"] = marked["height"]
        state["mode"] = "audio + camera"
    except Exception:
        state["vision_count"] = None
        state["boxes"] = []
        state["mode"] = "AUDIO ONLY - camera agent down"


def _phase(state):
    if state.get("halted"):
        return "HALTED"
    if state["close_requested"] and state["status"] == "BLOCK":
        return "CLOSE HELD"
    if state["close_requested"]:
        return "CLOSING"
    if "time_out" not in state["checklist"]:
        return "PRE-TIMEOUT"
    if state["removed"] < state["added"]:
        return "IN THE FIELD"
    return "COUNTING"


def _write(state):
    path = os.path.join(config.STATE_DIR, f"or{state['or']}.json")
    tmp = path + ".tmp"
    payload = json.dumps(state)
    for attempt in range(10):
        try:
            with open(tmp, "w", encoding="utf-8") as handle:
                handle.write(payload)
            os.replace(tmp, path)
            return
        except PermissionError:
            time.sleep(0.03 * (attempt + 1))
    with open(path, "w", encoding="utf-8") as handle:
        handle.write(payload)


def _sleep(seconds, stop):
    if seconds <= 0:
        return True
    end = time.time() + seconds
    while time.time() < end:
        if stop is not None and stop.is_set():
            return False
        time.sleep(min(0.05, max(0.0, end - time.time())))
    return True


def run_or(or_id, script, speed=4, hidden_problem=False, instant=False, persist=True,
           record_ledger=True, force_vision=False, stop=None, guard=None, script_name=None,
           procedure=None, scenario="complete", hold_tools=False):
    if isinstance(script, (list, tuple)):
        lines = list(script)
        name = script_name or "or1.json"
    else:
        name = os.path.basename(script)
        with open(script, encoding="utf-8") as handle:
            lines = json.load(handle)
    state = {
        "or": or_id,
        "script": name,
        "procedure": procedure or cases.procedure_for(name, hidden_problem),
        "expected": cases.expected_status(name, hidden_problem),
        "started": time.time(),
        "speed": speed,
        "added": 0,
        "removed": 0,
        "vision_count": None,
        "photo": None,
        "mode": "audio + camera",
        "checklist": [],
        "close_requested": False,
        "status": "SAFE",
        "alerts": [],
        "risk": 0,
        "message": "",
        "transcript": [],
        "latencies": [],
        "events": [],
        "done": False,
        "halted": False,
        "hidden": hidden_problem,
        "line_index": 0,
        "line_total": len(lines),
        "last_agents": None,
        "boxes": [],
        "tools_inside": [],
        "stitch_complete": False,
        "false_return": False,
        "frame_w": 480,
        "frame_h": 360,
        "tape": [],
        "op_phase": "SIGN IN",
        "scenario": scenario,
        "monitor_alert": "Case delayed after time-out. Incision has not started." if scenario == "delay" else "",
        "patient_log": [],
        "glucose": 108,
        "vitals": {"hr": 74, "sys": 118, "dia": 72, "spo2": 99, "rr": 14, "phase": "SIGN IN"},
        "phase": "PRE-TIMEOUT",
    }

    def save():
        state["phase"] = _phase(state)
        if guard is not None and not guard():
            return
        if persist:
            _write(state)

    def halted():
        state["halted"] = True
        state["done"] = True
        save()
        return state

    status, alerts, risk = fusion.evaluate(state)
    if status != state["status"]:
        state["message"] = agents.critic(state, status, alerts)
        if record_ledger:
            ledger.record({
                "type": "status", "or": or_id, "status": status, "alerts": alerts,
                "sponges_in": state["added"], "sponges_out": state["removed"],
                "camera": state["vision_count"],
            })
    state.update(status=status, alerts=alerts, risk=risk)
    _look(state, hidden_problem, force_vision)
    save()

    start = time.time()
    for index, line in enumerate(lines):
        if stop is not None and stop.is_set():
            return halted()
        if not instant:
            wait = line["t"] / speed - (time.time() - start)
            if not _sleep(wait, stop):
                return halted()
        t0 = time.perf_counter()
        try:
            counts, check = agents.process_line(line["text"])
        except Exception as exc:
            state["message"] = f"Language model unavailable: {type(exc).__name__}"
            save()
            continue
        state["last_agents"] = {
            "line": line["text"],
            "counter": counts,
            "checklist": check,
            "backend": agents.LAST.get("backend"),
            "ms": agents.LAST.get("ms"),
        }
        spoken = line["text"].lower()
        if "stitch is complete" in spoken or "stitching is complete" in spoken:
            state["stitch_complete"] = True
            state["op_phase"] = "STITCH CALLED"
        named = [name for name in ("hemostat", "needle", "scalpel", "forceps") if name in spoken]
        if "on the field" in spoken or "loaded" in spoken:
            for name in named:
                if name not in state["tools_inside"]:
                    state["tools_inside"].append(name)
        if "replaced" in spoken or "back on the tray" in spoken:
            if hidden_problem or hold_tools:
                state["false_return"] = True
            else:
                for name in named:
                    if name in state["tools_inside"]:
                        state["tools_inside"].remove(name)
        if any(word in spoken for word in ("scalpel", "incision", "hemostat", "suction", "needle", "specimen", "stitch")):
            state["op_phase"] = "IN THE OPERATION"
        elif "sponge out" in spoken or "counts are" in spoken:
            state["op_phase"] = "SPONGE COUNT"
        elif "let's close" in spoken or "lets close" in spoken:
            state["op_phase"] = "CLOSING"
        elif "time_out" in state["checklist"]:
            state["op_phase"] = state["op_phase"] if state["op_phase"] != "SIGN IN" else "PREPARED"
        beat = index + 1
        busy = state["op_phase"] == "IN THE OPERATION"
        state["vitals"] = {
            "hr": int(74 + (14 if busy else 0) + 6 * math.sin(beat / 2)),
            "sys": int(116 + (12 if busy else 0) + 4 * math.sin(beat / 3)),
            "dia": int(72 + (6 if busy else 0) + 3 * math.sin(beat / 3)),
            "spo2": 97 if busy else 99,
            "rr": 16 if busy else 13,
            "phase": state["op_phase"],
            "glucose": state.get("glucose", 108),
        }
        if scenario == "bp" and "incision" in spoken:
            state["vitals"].update(sys=186, dia=108, hr=110)
            state["monitor_alert"] = "BP malfunction: 186/108 during incision"
            state["patient_log"].append({"t": line["t"], "text": "Pressure rose to 186/108. Fluid infusion slowed."})
        elif scenario == "ecg" and "incision" in spoken:
            state["vitals"].update(hr=148)
            state["monitor_alert"] = "ECG irregular: heart rate 148"
            state["patient_log"].append({"t": line["t"], "text": "Rhythm changed. Heart rate 148 and irregular."})
        elif scenario == "bg" and "incision" in spoken:
            state["glucose"] = 54
            state["vitals"]["glucose"] = 54
            state["monitor_alert"] = "Blood glucose malfunction: 54 mg/dL"
            state["patient_log"].append({"t": line["t"], "text": "Glucose fell to 54. Dextrose infusion started."})
        elif scenario == "delay" and "scalpel" in spoken:
            state["monitor_alert"] = "Start was delayed. Incision is late."
            state["patient_log"].append({"t": line["t"], "text": "Patient waited. Incision started late."})
        elif "heart rate" in spoken:
            state["patient_log"].append({"t": line["t"], "text": line["text"] + " Infusion unchanged."})
        state["transcript"] = (state["transcript"] + [line["text"]])[-6:]
        state["added"] += counts["added"]
        state["removed"] += counts["removed"]
        if check["event"] != "none":
            if check["event"] not in state["checklist"]:
                state["checklist"].append(check["event"])
            state["events"].append({"t": line["t"], "event": check["event"], "detail": check["detail"]})
            if check["event"] == "close_requested":
                state["close_requested"] = True
        if counts["added"] or counts["removed"]:
            state["events"].append({
                "t": line["t"], "sponges_in": state["added"], "sponges_out": state["removed"],
            })
        _look(state, hidden_problem, force_vision)
        status, alerts, risk = fusion.evaluate(state)
        if status != state["status"]:
            try:
                state["message"] = agents.critic(state, status, alerts)
            except Exception:
                state["message"] = "; ".join(alerts)
            if record_ledger:
                ledger.record({
                    "type": "status", "or": or_id, "status": status, "alerts": alerts,
                    "sponges_in": state["added"], "sponges_out": state["removed"],
                    "camera": state["vision_count"],
                })
        state.update(status=status, alerts=alerts, risk=risk)
        if counts["removed"]:
            kind = "sponge-out"
        elif counts["added"]:
            kind = "sponge-in"
        elif check["event"] == "close_requested":
            kind = "close"
        elif check["event"] != "none":
            kind = "checklist"
        else:
            kind = "speech"
        state["tape"].append({
            "t": line["t"],
            "text": line["text"],
            "kind": kind,
            "photo": state.get("photo"),
            "boxes": [dict(box) for box in (state.get("boxes") or [])],
            "alerts": list(state.get("alerts") or []),
            "frame_w": state.get("frame_w") or 480,
            "frame_h": state.get("frame_h") or 360,
            "added": state["added"],
            "removed": state["removed"],
            "vision_count": state.get("vision_count"),
            "status": state["status"],
            "message": state.get("message") or "",
            "event": check["event"],
            "checklist": list(state["checklist"]),
            "vitals": dict(state["vitals"]),
            "model": {
                "added": counts["added"],
                "removed": counts["removed"],
                "event": check["event"],
                "detail": check.get("detail") or "",
                "backend": agents.LAST.get("backend") or "edge-local",
                "ms": agents.LAST.get("ms") or 0,
            },
        })
        state["tape"] = state["tape"][-80:]
        state["latencies"].append(round(time.perf_counter() - t0, 4))
        state["line_index"] = index + 1
        save()
    state["done"] = True
    save()
    return state


def replay(lines, hidden=False, script_name="or1.json"):
    return run_or(
        1, lines, speed=1, hidden_problem=hidden, instant=True, persist=False,
        record_ledger=False, force_vision=True, script_name=script_name,
    )


def clear_rooms():
    for path in glob.glob(os.path.join(config.STATE_DIR, "or*.json")):
        try:
            os.remove(path)
        except OSError:
            pass


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--ors", type=int, default=8)
    parser.add_argument("--speed", type=float, default=4)
    parser.add_argument("--problem", type=int, default=7)
    args = parser.parse_args()
    cases.install()
    photos.ensure()
    scripts = sorted(glob.glob(os.path.join(config.AUDIO_DIR, "*.json")))
    if not scripts:
        raise SystemExit("No transcripts in data/audio/.")
    clear_rooms()
    threads = [
        threading.Thread(
            target=run_or,
            kwargs={
                "or_id": i,
                "script": scripts[(i - 1) % len(scripts)],
                "speed": args.speed,
                "hidden_problem": i == args.problem,
            },
            daemon=True,
        )
        for i in range(1, args.ors + 1)
    ]
    print(f"Running {args.ors} rooms at {args.speed}x. Hidden problem in room {args.problem or 'none'}.")
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    print("All rooms finished.")


if __name__ == "__main__":
    main()
