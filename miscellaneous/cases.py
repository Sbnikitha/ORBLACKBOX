"""Acted operating-room transcripts. The simulator replays these with timing."""
import json
import os

import config


def _build(include_timeout, outs):
    lines = []
    t = 0.0

    def add(text, dt=2.4):
        nonlocal t
        lines.append({"t": round(t, 1), "text": text})
        t += dt

    if include_timeout:
        add("Let's do a time out.")
        add("Patient is John Doe, date of birth confirmed.")
        add("Laparoscopic appendectomy. Right side, site marked and confirmed.", 2.8)
        add("No known allergies.")
    add("Adding five sponges.")
    add("Adding five sponges.")
    add("Scalpel please.", 2.6)
    add("Incision is open. We are in the abdomen.", 2.6)
    add("Heart rate 86. Blood pressure 128 over 78. Oxygen 98.", 2.8)
    add("Hemostat on the field. Two clamps.", 2.4)
    add("Suction please.", 2.2)
    add("Needle driver loaded. One needle.", 2.4)
    add("Stitch is complete.", 2.4)
    add("Needle is back on the tray.", 2.2)
    add("Hemostat replaced on the tray.", 2.4)
    add("Specimen is out. Irrigation is clear.", 2.6)
    add("Heart rate 76. Blood pressure 114 over 70. Oxygen 99.", 2.6)
    for _ in range(outs):
        add("Sponge out.", 2.2)
    add("Counts are correct.", 2.6)
    add("Okay, let's close.", 2.4)
    return lines


CATALOG = [
    {
        "file": "or1.json",
        "procedure": "Lap appendectomy",
        "note": "Full time-out, 10 in and 10 out",
        "lines": _build(True, 10),
        "expect": "SAFE",
        "hidden_expect": "BLOCK",
    },
    {
        "file": "or2.json",
        "procedure": "Lap appendectomy",
        "note": "Spoken count short by one sponge",
        "lines": _build(True, 9),
        "expect": "BLOCK",
        "hidden_expect": "BLOCK",
    },
    {
        "file": "or3.json",
        "procedure": "Lap appendectomy",
        "note": "Time-out never spoken",
        "lines": _build(False, 10),
        "expect": "CAUTION",
        "hidden_expect": "BLOCK",
    },
]


def meta(filename):
    name = os.path.basename(filename)
    for case in CATALOG:
        if case["file"] == name:
            return case
    return None


def procedure_for(filename, hidden):
    case = meta(filename) or {}
    label = case.get("procedure", "Operating room")
    if hidden:
        return label + " · hidden tray"
    expect = case.get("expect")
    if expect == "BLOCK":
        return label + " · spoken mismatch"
    if expect == "CAUTION":
        return label + " · skipped time-out"
    return label


def expected_status(filename, hidden):
    case = meta(filename)
    if not case:
        return "SAFE"
    return case["hidden_expect"] if hidden else case["expect"]


PROCEDURES = {
    "appendectomy": "Laparoscopic appendectomy. Right side, site marked and confirmed.",
    "cholecystectomy": "Laparoscopic cholecystectomy. Right upper quadrant, site marked and confirmed.",
    "cesarean": "Cesarean section. Site marked and confirmed.",
    "knee": "Right knee arthroscopy. Site marked and confirmed.",
}


def build_case(procedure, focus):
    """One acted case from the live-screen choices."""
    outs = 9 if focus == "counts" else 10
    lines = _build(focus != "notimeout", outs)
    spoken = PROCEDURES.get(procedure, PROCEDURES["appendectomy"])
    built = []
    for line in lines:
        text = spoken if "site marked" in line["text"].lower() else line["text"]
        if focus == "allergy" and "allerg" in text.lower():
            continue
        built.append({"t": line["t"], "text": text})
    label = spoken.split(".")[0]
    if focus == "sponge":
        label += " · sponge missing"
    elif focus == "tool":
        label += " · tool left inside"
    elif focus == "counts":
        label += " · spoken count short"
    elif focus == "allergy":
        label += " · allergy not confirmed"
    elif focus == "delay":
        label += " · delayed start"
    elif focus == "bp":
        label += " · BP malfunction"
    elif focus == "ecg":
        label += " · ECG change"
    elif focus == "bg":
        label += " · glucose malfunction"
    else:
        label += " · complete case"
    return built, label


def install():
    os.makedirs(config.AUDIO_DIR, exist_ok=True)
    for case in CATALOG:
        path = os.path.join(config.AUDIO_DIR, case["file"])
        with open(path, "w", encoding="utf-8") as handle:
            json.dump(case["lines"], handle, indent=1)
            handle.write("\n")
    return [os.path.join(config.AUDIO_DIR, case["file"]) for case in CATALOG]
