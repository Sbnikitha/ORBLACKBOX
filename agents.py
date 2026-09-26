"""Counter, Checklist, Critic, and Scribe. Local edge models, or ZRT if configured."""
import json
import re
import time
import urllib.error
import urllib.request

import config
import local_model

LAST = {"backend": "edge-local", "ms": 0.0}


def _extract_json(text):
    text = re.sub(r"<think>.*?</think>", "", text or "", flags=re.S)
    match = re.search(r"\{.*\}", text, re.S)
    if not match:
        return {}
    try:
        return json.loads(match.group(0))
    except json.JSONDecodeError:
        return {}


def _safe_int(value):
    try:
        return max(int(value), 0)
    except (TypeError, ValueError):
        return 0


def _remote_chat(url, model, system, user, max_tokens=200):
    body = json.dumps({
        "model": model,
        "temperature": 0,
        "max_tokens": max_tokens,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
    }).encode()
    req = urllib.request.Request(
        url.rstrip("/") + "/chat/completions",
        data=body,
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=config.REQUEST_TIMEOUT_S) as res:
        data = json.loads(res.read().decode())
    return data["choices"][0]["message"]["content"]


def process_line(text):
    """Run Counter and Checklist on one line of speech."""
    started = time.perf_counter()
    backend = "edge-local"
    if config.LLM_URL.startswith("http"):
        try:
            from concurrent.futures import ThreadPoolExecutor
            counter_prompt = (
                'Reply ONLY with JSON {"added": int, "removed": int}. '
                "added = sponges opened. removed = sponges counted off the field."
            )
            check_prompt = (
                'Reply ONLY with JSON {"event": E, "detail": "short"}. '
                "E is time_out, patient_confirmed, site_confirmed, allergies_confirmed, "
                "count_confirmed, close_requested, or none."
            )
            with ThreadPoolExecutor(max_workers=2) as pool:
                c_job = pool.submit(_remote_chat, config.LLM_URL, config.LLM_MODEL, counter_prompt, text, 80)
                k_job = pool.submit(_remote_chat, config.LLM_URL, config.LLM_MODEL, check_prompt, text, 80)
                raw_c = _extract_json(c_job.result())
                raw_k = _extract_json(k_job.result())
            counts = {"added": _safe_int(raw_c.get("added")), "removed": _safe_int(raw_c.get("removed"))}
            event = local_model.normalize_event(raw_k.get("event", "none"))
            LAST.update(backend="zrt", ms=round((time.perf_counter() - started) * 1000, 1))
            return counts, {"event": event, "detail": raw_k.get("detail", "") or ""}
        except (urllib.error.URLError, TimeoutError, OSError, KeyError, json.JSONDecodeError):
            if not config.ALLOW_FALLBACK:
                raise
            backend = "edge-local-fallback"
    counts = local_model.counter(text)
    event = local_model.checklist(text)
    LAST.update(backend=backend, ms=round((time.perf_counter() - started) * 1000, 1))
    return counts, event


def critic(state, status, alerts):
    if config.LLM_URL.startswith("http"):
        try:
            raw = _extract_json(_remote_chat(
                config.LLM_URL, config.LLM_MODEL,
                'Reply ONLY with JSON {"message": "under 25 words for the nurse"}',
                json.dumps({"status": status, "alerts": alerts}),
                80,
            ))
            if raw.get("message"):
                return raw["message"]
        except (urllib.error.URLError, TimeoutError, OSError, KeyError, json.JSONDecodeError):
            if not config.ALLOW_FALLBACK:
                raise
    return local_model.critic(state, status, alerts)


def scribe(events, state=None):
    if config.LLM_URL.startswith("http"):
        try:
            text = _remote_chat(
                config.LLM_URL, config.LLM_MODEL,
                "Write a short surgical safety log in plain sentences.",
                json.dumps({"events": events, "state": state}, default=str),
                400,
            )
            return re.sub(r"<think>.*?</think>", "", text or "", flags=re.S).strip()
        except (urllib.error.URLError, TimeoutError, OSError, KeyError, json.JSONDecodeError):
            if not config.ALLOW_FALLBACK:
                raise
    return local_model.scribe(events, state)


def ask_protocol(question):
    if config.LLM_URL.startswith("http"):
        try:
            raw = _extract_json(_remote_chat(
                config.LLM_URL, config.LLM_MODEL,
                'Reply ONLY with JSON {"answer": "...", "confidence": number from 0 to 1}',
                question,
                220,
            ))
            conf = float(raw.get("confidence", 0))
            return {"answer": raw.get("answer", ""), "confidence": max(0.0, min(conf, 1.0)), "backend": "zrt"}
        except (urllib.error.URLError, TimeoutError, OSError, KeyError, json.JSONDecodeError, TypeError, ValueError):
            if not config.ALLOW_FALLBACK:
                raise
    result = local_model.protocol(question)
    result["backend"] = "edge-local"
    return result
