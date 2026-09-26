"""OR Sentinel command center API."""
import glob
import json
import os
import re
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
import cases
import cloud_router
import config
import engine
import ledger
import phi
import photos
import selftest
import trained
import vision

WEB = ROOT / "web"
_REPORT = {"report": None}


class CaseIn(BaseModel):
    procedure: str = "appendectomy"
    focus: str = "complete"
    room: int = 1


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


@app.post("/api/simulate")
def start_sim(body: SimIn):
    try:
        meta = engine.floor.start(body.ors, body.speed, body.problem)
    except RuntimeError as exc:
        raise HTTPException(400, str(exc)) from exc
    return {"ok": True, **meta}


@app.post("/api/case")
def start_case(body: CaseIn):
    meta = engine.floor.start_case(body.room, body.procedure, body.focus)
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


@app.get("/api/selftest")
def certified(force: bool = False):
    if _REPORT["report"] is None or force:
        _REPORT["report"] = selftest.run()
    return _REPORT["report"]


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


app.mount("/static", StaticFiles(directory=WEB), name="static")
