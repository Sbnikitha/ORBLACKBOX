"""Count sponges on a tray photo. Local TrayCount, or a vision model on ZRT."""
import base64
import json
import os
import re
import time
import urllib.error
import urllib.request

import config
import photos

LAST = {"backend": "traycount", "ms": 0.0}


def count_tray(path, force=False):
    """Return (count or None, seconds). Raises if the camera agent is cut and force is false."""
    if not force and os.path.exists(config.VISION_DOWN):
        raise ConnectionError("vision model offline")
    started = time.perf_counter()
    if str(config.VLM_URL).startswith("http"):
        try:
            mime = "image/png" if str(path).lower().endswith(".png") else "image/jpeg"
            with open(path, "rb") as handle:
                img = base64.b64encode(handle.read()).decode()
            body = json.dumps({
                "model": config.VLM_MODEL,
                "temperature": 0,
                "max_tokens": 8,
                "messages": [{"role": "user", "content": [
                    {"type": "image_url", "image_url": {"url": f"data:{mime};base64,{img}"}},
                    {"type": "text", "text": "How many gauze sponges are on the tray? Answer with a number only."},
                ]}],
            }).encode()
            req = urllib.request.Request(
                config.VLM_URL.rstrip("/") + "/chat/completions",
                data=body,
                headers={"Content-Type": "application/json"},
            )
            with urllib.request.urlopen(req, timeout=config.REQUEST_TIMEOUT_S) as res:
                data = json.loads(res.read().decode())
            match = re.search(r"\d+", data["choices"][0]["message"]["content"] or "")
            count = int(match.group(0)) if match else None
            LAST.update(backend="zrt-vision", ms=round((time.perf_counter() - started) * 1000, 1))
            return count, time.perf_counter() - started
        except (urllib.error.URLError, TimeoutError, OSError, KeyError, json.JSONDecodeError):
            if not config.ALLOW_FALLBACK:
                raise
    count = photos.count_image(path)
    LAST.update(backend="traycount", ms=round((time.perf_counter() - started) * 1000, 1))
    return count, time.perf_counter() - started
