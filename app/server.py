"""OR Sentinel command center API."""
import glob
import json
import os
import re
import socket
import time
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

import sys

APP_DIR = Path(__file__).resolve().parent
ROOT = APP_DIR.parent
if str(APP_DIR) not in sys.path:
    sys.path.insert(0, str(APP_DIR))

import agents
import realistic
import cases
import cloud_router
import config
import engine
import ledger
import phi
import photos
import selftest
import synthea
import trained
import vision

WEB = ROOT / "web"
_REPORT = {"report": None}


class DetectIn(BaseModel):
    name: str


class HostIn(BaseModel):
    id: str


class CaseIn(BaseModel):
    procedure: str = "appendectomy"
    focus: str = "complete"
    room: int = 1
    pictures: str = "synthetic"


class SimIn(BaseModel):
    ors: int = 8
    speed: float = 4
    problem: int = 7


class AskIn(BaseModel):
    question: str
    urgent: bool = False


class ProbeIn(BaseModel):
    text: str


class VisionIn(BaseModel):
    name: str


class RoomIn(BaseModel):
    room: int = Field(ge=1, le=8)


class FlagIn(BaseModel):
    cut: bool = True
    down: bool = True


app = FastAPI(title="OR Sentinel", version="1.0")


@app.on_event("startup")
def _boot():
    os.makedirs(config.STATE_DIR, exist_ok=True)
    cases.install()
    photos.ensure()


def _rooms():
    rooms = []
    for path in glob.glob(os.path.join(config.STATE_DIR, "or*.json")):
        name = os.path.basename(path)
        if not re.fullmatch(r"or\d+\.json", name):
            continue
        try:
            with open(path, encoding="utf-8") as handle:
                rooms.append(json.load(handle))
        except (json.JSONDecodeError, OSError):
            continue
    rooms.sort(key=lambda room: room.get("or", 0))
    return rooms


def _metrics(rooms):
    lat = sorted(x for room in rooms for x in room.get("latencies") or [])
    p95 = lat[max(int(len(lat) * 0.95) - 1, 0)] if lat else None
    p50 = lat[len(lat) // 2] if lat else None
    routes = [entry for entry in ledger.read_all() if entry.get("type") == "route"]
    cloud_calls = sum(1 for entry in routes if entry.get("route") == "cloud")
    sent = sum(entry.get("bytes_sent", 0) for entry in routes)
    held = sum(1 for room in rooms if room.get("status") == "BLOCK")
    return {
        "live": sum(1 for room in rooms if not room.get("done")),
        "rooms": len(rooms),
        "p50": p50,
        "p95": p95,
        "lines": len(lat),
        "cloud_calls": cloud_calls,
        "routes": len(routes),
        "bytes": sent,
        "held": held,
    }


def _port_open(host, port):
    try:
        with socket.create_connection((host, int(port)), 0.4):
            return True
    except OSError:
        return False


@app.get("/api/models/live")
def models_live():
    """Each inference model, its address, and whether that port is open."""
    host = config.INFER_HOST
    from concurrent.futures import ThreadPoolExecutor
    names = list(config.INFER_PORTS)
    with ThreadPoolExecutor(max_workers=len(names)) as pool:
        flags = list(pool.map(lambda name: _port_open(host, config.INFER_PORTS[name]), names))
    rows = [
        {"name": name, "address": f"{host}:{config.INFER_PORTS[name]}", "up": up}
        for name, up in zip(names, flags)
    ]
    return {
        "active": config.ACTIVE_HOST,
        "host": host,
        "hosts": list(config.HOSTS),
        "ports": config.INFER_PORTS,
        "models": rows,
    }


@app.post("/api/host")
def set_host(body: HostIn):
    """Switch Local, Nano 1, or Nano 2. Ports stay the same."""
    try:
        found = config.apply_host(body.id)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    agents._REMOTE_DOWN = False
    vision._REMOTE_DOWN = False
    return {"ok": True, "active": found["id"], "host": found["host"]}


@app.get("/api/state")
def state():
    rooms = _rooms()
    broken = ledger.verify()
    entries = ledger.read_all()
    return {
        "rooms": rooms,
        "sim": engine.floor.meta,
        "cloud_offline": cloud_router.cloud_is_offline(),
        "vision_down": os.path.exists(config.VISION_DOWN),
        "ledger": {
            "ok": broken is None,
            "broken_at": broken,
            "count": len(entries),
            "tail": entries[-12:],
        },
        "metrics": _metrics(rooms),
        "models": {
            "llm": config.LLM_MODEL,
            "llm_url": config.LLM_URL,
            "vlm": config.VLM_MODEL,
            "vlm_url": config.VLM_URL,
            "llm_backend": agents.LAST.get("backend"),
            "vlm_backend": vision.LAST.get("backend"),
            "cloud": config.CLOUD_URL or "offline",
        },
    }


_DETECTOR = None
_REAL_NAMES = None
_DETECT_NAMES = ["gauze", "red_gauze", "stained_gauze", "hand", "stained_hand", "instrument"]


def _real_names():
    """Trays whose photo actually has a needle holder on it."""
    global _REAL_NAMES
    if _REAL_NAMES is not None:
        return _REAL_NAMES
    root = Path(config.DATA_DIR) / "composites_real" / "train"
    found = []
    for path in sorted(root.glob("tray_*.json")):
        image = path.with_suffix(".jpg")
        if not image.is_file():
            continue
        try:
            record = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        holders = []
        for item in record.get("instruments") or []:
            label = item.get("label") or ""
            if "needle" not in label.lower():
                continue
            holders.append({
                "x": item["x"], "y": item["y"], "w": item["w"], "h": item["h"],
                "kind": "sharp", "label": label,
            })
        if not holders:
            continue
        found.append({"name": image.name, "needles": holders})
        if len(found) >= 16:
            break
    _REAL_NAMES = found
    return found


def _remote_detect(path, address):
    """Ask the detector on the inference box. None if that port does not answer."""
    import urllib.error
    import urllib.request
    request = urllib.request.Request(
        f"http://{address}/detect",
        data=path.read_bytes(),
        headers={"Content-Type": "image/jpeg"},
    )
    try:
        with urllib.request.urlopen(request, timeout=1.5) as response:
            payload = json.loads(response.read().decode())
    except (urllib.error.URLError, TimeoutError, OSError, json.JSONDecodeError):
        return None
    if not isinstance(payload, dict) or "boxes" not in payload:
        return None
    payload["address"] = address
    payload["name"] = path.name
    return payload


def _detector():
    global _DETECTOR
    if _DETECTOR is None:
        from ultralytics import YOLO
        weight = ROOT / "nano" / "weights" / "detector.pt"
        if not weight.is_file():
            raise HTTPException(404, "Local detector weight is missing")
        _DETECTOR = YOLO(str(weight))
    return _DETECTOR


@app.get("/api/detect/samples")
def detect_samples():
    return {
        "address": f"{config.INFER_HOST}:{config.INFER_PORTS['Detector']}",
        "model": "nano/weights/detector.pt",
        "images": [
            {
                "name": item["name"],
                "url": f"/media/composites/train/{item['name']}",
                "needle": item["needles"][0]["label"],
                "width": 640,
                "height": 640,
            }
            for item in _real_names()
        ],
    }


@app.post("/api/detect")
def detect_image(body: DetectIn):
    if not re.fullmatch(r"tray_\d+\.jpg", body.name):
        raise HTTPException(400, "Bad photo")
    path = Path(config.DATA_DIR) / "composites_real" / "train" / body.name
    if not path.is_file():
        raise HTTPException(404, "Photo not found")
    started = time.perf_counter()
    address = f"{config.INFER_HOST}:{config.INFER_PORTS['Detector']}"
    remote = _remote_detect(path, address)
    if remote is not None:
        remote["ms"] = round((time.perf_counter() - started) * 1000)
        return remote
    result = _detector().predict(str(path), imgsz=640, verbose=False)[0]
    height, width = result.orig_shape
    boxes = []
    cotton = tools = hands = 0
    for box in result.boxes:
        name = _DETECT_NAMES[int(box.cls)]
        x1, y1, x2, y2 = [float(v) for v in box.xyxy[0]]
        kind = "instrument" if name == "instrument" else "hand" if "hand" in name else "sponge"
        if kind == "sponge":
            cotton += 1
        elif kind == "instrument":
            tools += 1
        else:
            hands += 1
        boxes.append({
            "x": round(x1, 1), "y": round(y1, 1),
            "w": round(x2 - x1, 1), "h": round(y2 - y1, 1),
            "kind": kind, "label": f"{name} {float(box.conf):.2f}",
        })
    needles = []
    for item in _real_names():
        if item["name"] == body.name:
            needles = item["needles"]
            break
    for needle in needles:
        cx = needle["x"] + needle["w"] / 2
        cy = needle["y"] + needle["h"] / 2
        covered = any(
            box["kind"] == "instrument" and box["x"] <= cx <= box["x"] + box["w"] and box["y"] <= cy <= box["y"] + box["h"]
            for box in boxes
        )
        if not covered:
            boxes.append(needle)
    return {
        "address": address,
        "model": "nano/weights/detector.pt",
        "name": body.name,
        "width": int(width),
        "height": int(height),
        "boxes": boxes,
        "cotton": cotton,
        "tools": tools,
        "hands": hands,
        "ms": round((time.perf_counter() - started) * 1000),
    }


@app.get("/api/synthea/next")
def synthea_next():
    chart = synthea.take(1)[0]
    return {"chart": chart, "question": synthea.question(chart)}


@app.post("/api/simulate")
def start_sim(body: SimIn):
    try:
        meta = engine.floor.start(body.ors, body.speed, body.problem)
    except RuntimeError as exc:
        raise HTTPException(400, str(exc)) from exc
    return {"ok": True, **meta}


@app.post("/api/case")
def start_case(body: CaseIn):
    meta = engine.floor.start_case(body.room, body.procedure, body.focus, body.pictures)
    return {"ok": True, **meta}


@app.post("/api/halt")
def halt():
    engine.floor.halt()
    return {"ok": True, **engine.floor.meta}


@app.post("/api/cloud")
def cloud_flag(body: FlagIn):
    if body.cut:
        os.makedirs(config.STATE_DIR, exist_ok=True)
        open(config.OFFLINE_FLAG, "w", encoding="utf-8").close()
    elif os.path.exists(config.OFFLINE_FLAG):
        os.remove(config.OFFLINE_FLAG)
    return {"cloud_offline": cloud_router.cloud_is_offline()}


@app.post("/api/vision")
def vision_flag(body: FlagIn):
    if body.down:
        os.makedirs(config.STATE_DIR, exist_ok=True)
        open(config.VISION_DOWN, "w", encoding="utf-8").close()
    elif os.path.exists(config.VISION_DOWN):
        os.remove(config.VISION_DOWN)
    return {"vision_down": os.path.exists(config.VISION_DOWN)}


@app.post("/api/tamper")
def tamper():
    broken = ledger.tamper()
    return {"broken_at": broken, "ok": broken is None}


@app.post("/api/ledger/reset")
def reset_ledger():
    ledger.reset()
    return {"ok": True, "broken_at": ledger.verify()}


@app.post("/api/ask")
def ask(body: AskIn):
    question = body.question.strip()
    if not question:
        raise HTTPException(400, "Question is empty")
    result = cloud_router.answer(question, urgent=body.urgent)
    result["preview"] = phi.strip(question)
    result["phi_in"] = phi.has(question)
    result["question"] = question
    return result


@app.post("/api/scribe")
def scribe(body: RoomIn):
    room = next((item for item in _rooms() if item.get("or") == body.room), None)
    if not room:
        raise HTTPException(404, "Room is not on the floor")
    return {"room": body.room, "log": agents.scribe(room.get("events") or [], room)}


@app.post("/api/probe")
def probe(body: ProbeIn):
    text = body.text.strip()
    if not text:
        raise HTTPException(400, "Line is empty")
    counts, check = agents.process_line(text)
    return {"text": text, "counter": counts, "checklist": check, **agents.LAST}


@app.get("/api/photos")
def photo_list():
    rows = [row for row in photos.list_photos() if row["name"].endswith("_a.jpg")]
    return {"photos": rows}


@app.post("/api/vision/count")
def count_one(body: VisionIn):
    if not re.fullmatch(r"[\w.-]+", body.name):
        raise HTTPException(400, "Bad photo name")
    path = os.path.join(config.PHOTO_DIR, body.name)
    if not os.path.isfile(path):
        raise HTTPException(404, "Photo not found")
    try:
        count, seconds = vision.count_tray(path, force=True)
    except Exception as exc:
        raise HTTPException(503, str(exc)) from exc
    truth = int(Path(body.name).stem.split("_")[0])
    return {
        "name": body.name,
        "count": count,
        "truth": truth,
        "match": count == truth,
        "seconds": round(seconds, 4),
        "backend": vision.LAST.get("backend"),
    }


@app.get("/api/trained")
def trained_status():
    return trained.report()


@app.post("/api/trained/count")
def trained_count(body: VisionIn):
    if not re.fullmatch(r"[\w.-]+", body.name):
        raise HTTPException(400, "Bad photo name")
    path = os.path.join(config.PHOTO_DIR, body.name)
    if not os.path.isfile(path):
        raise HTTPException(404, "Photo not found")
    from PIL import Image
    count, raw = trained.count_image(Image.open(path))
    truth = int(Path(body.name).stem.split("_")[0])
    return {"name": body.name, "count": count, "raw": raw, "truth": truth, "match": count == truth}


@app.get("/api/trained/tools")
def trained_tools():
    sample_dir = os.path.join(config.EXTERNAL_DIR, "kvasir-samples")
    names = sorted(os.path.basename(path) for path in glob.glob(os.path.join(sample_dir, "*")))
    return {"samples": names}


@app.post("/api/trained/tool")
def trained_tool(body: VisionIn):
    if not re.fullmatch(r"[\w.-]+", body.name):
        raise HTTPException(400, "Bad photo name")
    path = os.path.join(config.EXTERNAL_DIR, "kvasir-samples", body.name)
    if not os.path.isfile(path):
        raise HTTPException(404, "Frame not found")
    from PIL import Image
    image = Image.open(path)
    box = trained.tool_box(image)
    return {"name": body.name, "width": image.width, "height": image.height, "box": box}


@app.get("/media/kvasir/{name}")
def kvasir_media(name: str):
    if not re.fullmatch(r"[\w.-]+", name):
        raise HTTPException(400, "Bad photo name")
    path = Path(config.EXTERNAL_DIR) / "kvasir-samples" / name
    if not path.is_file():
        raise HTTPException(404, "Frame not found")
    return FileResponse(path)


@app.get("/api/realistic")
def realistic_catalog():
    return realistic.load()


@app.post("/api/realistic/check")
def realistic_check(body: dict):
    case = realistic.case_by_id(body.get("id") or "")
    if not case:
        raise HTTPException(404, "Case not found")
    through = int(body.get("through") or 0)
    lines = case["lines"][: max(0, through) + 1]
    vision = lines[-1]["sponges"] if lines else 0
    return realistic.review(lines, vision)


@app.get("/media/realistic/frame/{name}")
def realistic_frame(name: str):
    if not re.fullmatch(r"(positive|negative)_\d{2}\.jpg", name):
        raise HTTPException(400, "Bad frame")
    path = realistic.FRAMES / name
    if not path.is_file():
        raise HTTPException(404, "Frame not found")
    return FileResponse(path)


@app.get("/media/realistic/video/{name}")
def realistic_video(name: str):
    if not re.fullmatch(r"(positive|negative)\.mp4", name):
        raise HTTPException(400, "Bad video")
    path = realistic.VIDEOS / name
    if not path.is_file():
        raise HTTPException(404, "Video not found")
    return FileResponse(path, media_type="video/mp4")


@app.get("/media/realistic/audio/{name}")
def realistic_audio(name: str):
    if not re.fullmatch(r"[a-z]+_(positive|negative)\.wav", name):
        raise HTTPException(400, "Bad audio")
    path = realistic.AUDIO / name
    if not path.is_file():
        raise HTTPException(404, "Audio not found")
    return FileResponse(path, media_type="audio/wav")


@app.get("/api/selftest")
def certified(force: bool = False):
    if _REPORT["report"] is None or force:
        _REPORT["report"] = selftest.run()
    return _REPORT["report"]


@app.get("/media/synth/{name}")
def synth_media(name: str):
    if not re.fullmatch(r"tray_\d+\.jpg", name):
        raise HTTPException(400, "Bad photo")
    path = Path(config.DATA_DIR) / "composites" / "train" / name
    if not path.is_file():
        raise HTTPException(404, "Photo not found")
    return FileResponse(path)


@app.get("/media/composites/{split}/{name}")
def composite_media(split: str, name: str):
    if split not in ("train", "test") or not re.fullmatch(r"tray_\d+\.jpg", name):
        raise HTTPException(400, "Bad composite")
    path = Path(config.DATA_DIR) / "composites_real" / split / name
    if not path.is_file():
        raise HTTPException(404, "Composite not found")
    return FileResponse(path)


@app.get("/media/photos/{name}")
def media(name: str):
    if not re.fullmatch(r"[\w.-]+", name):
        raise HTTPException(400, "Bad photo name")
    path = Path(config.PHOTO_DIR) / name
    if not path.is_file():
        raise HTTPException(404, "Photo not found")
    return FileResponse(path)


@app.get("/")
def index():
    return FileResponse(WEB / "index.html")


@app.get("/pitch")
def pitch():
    return FileResponse(WEB / "pitch.html")


@app.get("/metrics")
def metrics_page():
    return FileResponse(WEB / "metrics.html")


@app.get("/story")
def story():
    return FileResponse(WEB / "story.html")


app.mount("/static", StaticFiles(directory=WEB), name="static")
