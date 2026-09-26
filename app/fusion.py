"""Fixed rules decide SAFE, CAUTION, or BLOCK. The models only read and explain."""
import time

import config


def evaluate(state):
    """Return (status, alerts, risk 0-100) for one operating room."""
    alerts = []
    risk = 0
    missing = state["added"] - state["removed"]
    cam = state.get("vision_count")
    camera_disagrees = cam is not None and cam != state["removed"]
    if camera_disagrees:
        alerts.append(
            f"Nurse counted {state['removed']} out, camera sees {cam} on the tray"
        )
        risk += 40
    if "time_out" not in state["checklist"]:
        alerts.append("Time-out not done yet")
        risk += 15
    inside = list(state.get("tools_inside") or [])
    if inside and (state.get("stitch_complete") or state["close_requested"]):
        alerts.append(
            "Tool still inside: " + ", ".join(inside) + ". Not replaced on the tray."
        )
        risk += 35
    if state.get("monitor_alert"):
        alerts.append(state["monitor_alert"])
        risk += 25
    if state.get("false_return") and inside:
        alerts.append("Team said a tool was replaced. The tray camera does not show it back.")
        risk += 20
    if state["close_requested"] and missing != 0:
        alerts.append(f"Count mismatch: {state['added']} in, {state['removed']} out")
        risk += 45
    minutes = (time.time() - state["started"]) / 60 * state.get("speed", 1)
    if minutes > config.LONG_SURGERY_MIN:
        alerts.append("Surgery over 6 hours: higher error risk")
        risk += 10
    if state["close_requested"] and (missing != 0 or camera_disagrees or inside):
        status = "BLOCK"
    elif alerts:
        status = "CAUTION"
    else:
        status = "SAFE"
    return status, alerts, min(risk, 100)
