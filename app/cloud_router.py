"""Local vs cloud. Urgent, confident, or offline stays local. Otherwise strip, recheck, then send."""
import json
import os
import urllib.error
import urllib.request

import agents
import config
import ledger
import phi


def cloud_is_offline():
    return os.path.exists(config.OFFLINE_FLAG) or not config.CLOUD_URL


def reason_for(urgent, confidence, offline, phi_left):
    if urgent:
        return "urgent"
    if confidence >= config.CONFIDENCE_THRESHOLD:
        return "confident"
    if offline:
        return "cloud offline"
    if phi_left:
        return "patient data remained"
    return "cloud"


def _cloud_complete(clean):
    if config.CLOUD_URL in ("simulated", "local"):
        text = agents.ask_protocol(clean)["answer"]
        return "[protocol desk] " + text
    body = json.dumps({
        "model": config.CLOUD_MODEL,
        "max_tokens": 220,
        "messages": [{"role": "user", "content": clean}],
    }).encode()
    req = urllib.request.Request(
        config.CLOUD_URL.rstrip("/") + "/chat/completions",
        data=body,
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {config.CLOUD_KEY}",
        },
    )
    with urllib.request.urlopen(req, timeout=15) as res:
        data = json.loads(res.read().decode())
    return data["choices"][0]["message"]["content"]


def answer(question, urgent=False):
    """Return route, answer, sent payload, and confidence. sent is exactly what left the box."""
    local = agents.ask_protocol(question)
    try:
        conf = float(local.get("confidence", 0))
    except (TypeError, ValueError):
        conf = 0.0
    local_answer = local.get("answer", "")
    offline = cloud_is_offline()
    clean = phi.strip(question)
    phi_left = phi.has(clean)
    why = reason_for(urgent, conf, offline, phi_left)

    def stay(why_now):
        ledger.record({
            "type": "route", "route": "local", "reason": why_now,
            "confidence": conf, "bytes_sent": 0,
        })
        return {
            "route": f"local ({why_now})",
            "reason": why_now,
            "answer": local_answer,
            "sent": "",
            "confidence": conf,
            "bytes_sent": 0,
            "backend": local.get("backend", "edge-local"),
        }

    if why != "cloud":
        return stay(why)
    try:
        cloud_text = _cloud_complete(clean)
        sent_bytes = len(clean.encode())
        ledger.record({
            "type": "route", "route": "cloud", "reason": "low confidence",
            "confidence": conf, "bytes_sent": sent_bytes,
        })
        return {
            "route": "cloud",
            "reason": "cloud",
            "answer": cloud_text,
            "sent": clean,
            "confidence": conf,
            "bytes_sent": sent_bytes,
            "backend": "protocol-desk",
        }
    except (urllib.error.URLError, TimeoutError, OSError, KeyError, json.JSONDecodeError):
        return stay("cloud unreachable")
