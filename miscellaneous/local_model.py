"""On-box stand-ins for the four language agents and the protocol desk.

These are the models the floor runs when ZRT is not attached. They follow the
same JSON contracts as the 27B prompts in the implementation guide.
"""
import re

import phi

_WORDS = {
    "a": 1, "an": 1, "one": 1, "two": 2, "three": 3, "four": 4, "five": 5,
    "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10, "eleven": 11,
    "twelve": 12, "fifteen": 15,
}

_EVENTS = (
    "time_out", "patient_confirmed", "site_confirmed", "allergies_confirmed",
    "count_confirmed", "close_requested", "none",
)

# Low-confidence prompts are checked first so they can escalate.
_PROTOCOL = [
    (
        ("most often skip", "skip instrument"),
        0.41,
        "Counts are still required. Do not guess which specialty skipped them. Stop and follow the count policy for this case.",
    ),
    (
        ("counts are required", "before closing", "which counts"),
        0.94,
        "Before closing, the circulating nurse confirms sponges, sharps, and instruments. The cavity stays open until the spoken count and the tray agree.",
    ),
    (
        ("three phases", "who surgical"),
        0.95,
        "The WHO checklist has three phases: Sign In before anesthesia, Time Out before incision, and Sign Out before the patient leaves the room.",
    ),
    (
        ("count is incorrect", "sponge count is incorrect", "incorrect before closing"),
        0.93,
        "Stop the close. Search the field, the floor, and the trash. If the item is still missing, get an X-ray and document every step.",
    ),
    (
        ("usually counted", "open abdominal", "items are usually"),
        0.9,
        "Open abdominal cases usually count sponges, sharps, and instruments at baseline, at cavity closure, and at skin closure.",
    ),
    (
        ("sharps count",),
        0.92,
        "Yes. A sharps count is part of the standard count with sponges and instruments, and it is repeated before closing.",
    ),
    (
        ("retained surgical",),
        0.96,
        "A retained surgical item is a sponge, instrument, or needle left in the patient. It is a never event. The count is the interlock that stops it.",
    ),
    (
        ("x-ray", "intraoperative"),
        0.9,
        "Consider an intraoperative X-ray when the count is wrong and the missing item is not found in the field.",
    ),
    (
        ("sign-out", "sign out"),
        0.91,
        "At sign-out the nurse confirms the procedure name, sponge and instrument counts, specimen labels, and recovery concerns.",
    ),
    (
        ("cesarean",),
        0.9,
        "Yes. Cesarean counts are done before uterine closure and again before skin closure.",
    ),
    (
        ("purpose of the time-out", "time-out before incision", "timeout before"),
        0.94,
        "The time-out confirms the right patient, site, and procedure, with the whole team present, before the incision.",
    ),
    (
        ("allerg",),
        0.9,
        "At sign-in, confirm drug, latex, and antiseptic allergies out loud and record them before anesthesia.",
    ),
    (
        ("shift change",),
        0.92,
        "On a shift change, the outgoing and incoming nurses count together and both sign the record before the handoff is done.",
    ),
    (
        ("radiopaque",),
        0.93,
        "Radiopaque sponges show up on X-ray. Non-radiopaque sponges do not, so a missing one is harder to find and must be treated as still in the field.",
    ),
    (
        ("documentation", "discrepancy"),
        0.88,
        "After a discrepancy, document the search, the X-ray result, who was told, and the final count before the patient leaves.",
    ),
    (
        ("wrong-site", "wrong site"),
        0.94,
        "Wrong-site surgery is an operation on the wrong side, level, or patient. Mark the site and complete the time-out before incision.",
    ),
    (
        ("refuses to pause", "refuses to"),
        0.9,
        "If the surgeon will not pause for a recount, do not close. Escalate to the charge nurse, keep the field open, and write it down.",
    ),
    (
        ("sign-in", "sign in", "anesthesia induction"),
        0.92,
        "Sign-in, before anesthesia, confirms identity, site, procedure, consent, allergies, airway risk, and expected blood loss.",
    ),
]


def _num(token):
    token = token.lower().strip(" .,")
    if token.isdigit():
        return int(token)
    return _WORDS.get(token, 0)


def counter(text):
    """Sponges added or removed in one spoken line."""
    raw = (text or "").lower()
    added = removed = 0
    found = re.search(r"add(?:ing|ed)?\s+(\w+)\s+sponges?", raw)
    if found:
        added = _num(found.group(1))
    found = re.search(r"(\w+)\s+sponges?\s+out", raw)
    if found and _num(found.group(1)):
        removed = _num(found.group(1))
    elif re.search(r"sponges?\s+out", raw):
        removed = 1
    return {"added": added, "removed": removed}


def checklist(text):
    """One WHO checklist event from one spoken line."""
    raw = (text or "").lower()
    if "time out" in raw or "time-out" in raw or "timeout" in raw:
        return {"event": "time_out", "detail": ""}
    if "patient" in raw and ("confirm" in raw or "date of birth" in raw or "dob" in raw):
        return {"event": "patient_confirmed", "detail": ""}
    if "site" in raw and ("marked" in raw or "confirm" in raw):
        if "right" in raw:
            detail = "right side"
        elif "left" in raw:
            detail = "left side"
        else:
            detail = ""
        return {"event": "site_confirmed", "detail": detail}
    if "allerg" in raw:
        detail = "none" if ("no known" in raw or "nkda" in raw) else ""
        return {"event": "allergies_confirmed", "detail": detail}
    if (
        "counts are correct" in raw
        or "count is correct" in raw
        or "counts correct" in raw
        or "count confirmed" in raw
    ):
        return {"event": "count_confirmed", "detail": ""}
    if re.search(r"(let's|lets|let us)\s+close", raw) or "ready to close" in raw:
        return {"event": "close_requested", "detail": ""}
    return {"event": "none", "detail": ""}


def critic(state, status, alerts):
    """One sentence for the circulating nurse. Rules already chose the status."""
    added = state.get("added")
    removed = state.get("removed")
    cam = state.get("vision_count")
    camera = any("camera" in a.lower() for a in alerts)
    mismatch = any("mismatch" in a.lower() for a in alerts)
    if any("still inside" in a.lower() for a in alerts):
        held = ", ".join(state.get("tools_inside") or []) or "a tool"
        if status == "BLOCK":
            return f"Do not close. {held} is still inside and was not replaced on the tray."
        return f"Stitch is not finished. {held} is still inside. Put it back on the tray."
    if status == "BLOCK":
        if camera and mismatch:
            return (
                f"Do not close. Spoken count is {added} in and {removed} out, "
                f"and the camera sees {cam}. Find the missing sponge."
            )
        if camera:
            return (
                f"Do not close. Camera sees {cam} on the tray and the nurse counted {removed} out."
            )
        if mismatch:
            return f"Do not close. {added} sponges went in and only {removed} came out."
        return "Do not close. Resolve the count before the incision is closed."
    if status == "CAUTION":
        if any("Time-out" in a for a in alerts):
            return "Time-out is not complete. Confirm patient, site, and allergies before incision."
        if camera:
            return "Camera and the spoken out-count disagree. Recount the tray now."
        if any("6 hours" in a for a in alerts):
            return "This case is past six hours. Slow down and repeat the count."
        return alerts[0] if alerts else "Check the count before you continue."
    return "Counts agree and the checklist is complete. Safe to proceed."


def scribe(events, state=None):
    """Plain-language safety log from the event list."""
    lines = ["Surgical safety log."]
    for event in events or []:
        stamp = event.get("t", "?")
        if event.get("event"):
            name = str(event["event"]).replace("_", " ")
            detail = event.get("detail") or ""
            extra = f" ({detail})" if detail else ""
            lines.append(f"At {stamp}s, checklist marked {name}{extra}.")
        if "sponges_in" in event:
            lines.append(
                f"At {stamp}s, running count is {event['sponges_in']} in and {event['sponges_out']} out."
            )
    if state:
        cam = state.get("vision_count")
        cam_txt = "no camera reading" if cam is None else f"camera {cam}"
        lines.append(
            f"Final status {state.get('status')}. "
            f"Sponges in {state.get('added')}, out {state.get('removed')}, {cam_txt}."
        )
        if state.get("alerts"):
            lines.append("Alerts: " + "; ".join(state["alerts"]) + ".")
    if len(lines) == 1:
        lines.append("No events recorded.")
    return "\n".join(lines)


def protocol(question):
    """Local answer plus a confidence score from 0 to 1."""
    raw = question or ""
    folded = raw.lower()
    answer = "Check the hospital count policy with the charge nurse. This station is not sure enough to treat that as complete."
    confidence = 0.48
    for keys, conf, text in _PROTOCOL:
        if any(key in folded for key in keys):
            answer = text
            confidence = conf
            break
    if phi.has(raw):
        confidence = min(confidence, 0.55)
    return {"answer": answer, "confidence": confidence}


def normalize_event(event):
    if event not in _EVENTS:
        return "none"
    return event
