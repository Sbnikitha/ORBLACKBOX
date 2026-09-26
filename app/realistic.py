"""One appendectomy, one tray, two cases.

Every frame is the same tray photo. Only the cotton count and the tool count
change. Each case is one video, one audio track, and one blood-pressure reading.
Positive: the tray matches the words and the pressure is normal, so close is SAFE.
Negative: the tray is one cotton and one tool short, and the pressure is low,
so close is BLOCK.
"""
import json
import re
import sys
import time
import wave
from pathlib import Path

import numpy as np
from PIL import Image

import agents
import config
import fusion

DIR = Path(config.DATA_DIR) / "realistic"
FRAMES = DIR / "frames"
AUDIO = DIR / "audio"
VIDEOS = DIR / "video"
CATALOG = DIR / "catalog.json"
ROOT = Path(config.DATA_DIR).parent
SAID_TOOLS = 3

BEATS = [
    ("Let's do a time out.", 0, 0),
    ("Patient is confirmed. Date of birth confirmed.", 0, 0),
    ("Laparoscopic appendectomy. Right side, site marked and confirmed.", 0, 0),
    ("No known allergies.", 0, 0),
    ("Adding five sponges.", 5, 1),
    ("Adding five sponges.", 10, 2),
    ("Three instruments on the tray.", 10, 3),
    ("__bp__", 10, 3),
    ("Ten sponges out.", None, None),
    ("Counts are correct.", None, None),
    ("Okay, let's close.", None, None),
]


def _script(positive):
    pressure = "Blood pressure 118 over 72." if positive else "Blood pressure 86 over 48."
    cotton_out = 10 if positive else 9
    tools_out = 3 if positive else 2
    rows = []
    for text, cotton, tools in BEATS:
        if text == "__bp__":
            text = pressure
        if cotton is None:
            cotton, tools = cotton_out, tools_out
        rows.append({"text": text, "sponges": cotton, "tools": tools})
    return rows


def _monitor(text):
    if "86 over 48" in text.lower():
        return "Blood pressure 86/48"
    return ""


def review(lines, vision_count):
    """Run Counter, Checklist, and the rules on the lines heard so far."""
    state = {
        "added": 0,
        "removed": 0,
        "checklist": [],
        "vision_count": vision_count,
        "tools_inside": [],
        "stitch_complete": False,
        "false_return": False,
        "close_requested": False,
        "monitor_alert": "",
        "started": time.time(),
        "speed": 1,
    }
    counting_out = any(re.search(r"sponges?\s+out", line["text"], re.I) for line in lines)
    if not counting_out:
        vision_count = None
    state["vision_count"] = vision_count
    said_tools = any("instrument" in line["text"].lower() for line in lines)
    on_tray = lines[-1]["tools"] if lines else 0
    if said_tools and on_tray < SAID_TOOLS:
        state["tools_inside"] = ["instrument"]
    heard = []
    for line in lines:
        counts, check = agents.process_line(line["text"])
        state["added"] += counts["added"]
        state["removed"] += counts["removed"]
        event = check.get("event")
        if event and event != "none" and event not in state["checklist"]:
            state["checklist"].append(event)
        if event == "close_requested":
            state["close_requested"] = True
        alert = _monitor(line["text"])
        if alert:
            state["monitor_alert"] = alert
        heard.append({
            "text": line["text"],
            "added": counts["added"],
            "removed": counts["removed"],
            "event": event,
            "sponges": line["sponges"],
            "tools": line["tools"],
        })
    status, alerts, risk = fusion.evaluate(state)
    return {
        "status": status,
        "alerts": alerts,
        "risk": risk,
        "added": state["added"],
        "removed": state["removed"],
        "vision_count": vision_count,
        "tools": on_tray,
        "checklist": state["checklist"],
        "heard": heard,
    }


def _pick_tray():
    nano = ROOT / "nano"
    if str(nano) not in sys.path:
        sys.path.insert(0, str(nano))
    import compose_real

    root = Path(config.EXTERNAL_DIR) / "igauze"
    names = compose_real._class_names(root)
    labels = root / "train" / "labels"
    images = root / "train" / "images"
    best = None
    for label_path in labels.glob("*.txt"):
        image_path = None
        for suffix in (".jpg", ".jpeg", ".png"):
            candidate = images / (label_path.stem + suffix)
            if candidate.is_file():
                image_path = candidate
                break
        if image_path is None:
            continue
        with Image.open(image_path) as image:
            width, height = image.size
        boxes = compose_real._boxes(label_path, names, width, height)
        gauze = [box for box in boxes if box["kind"] == "gauze"]
        hands = [box for box in boxes if box["kind"] == "hand"]
        if len(gauze) < 10 or hands:
            continue
        score = (abs(len(gauze) - 10), width * height)
        if best is None or score < best[0]:
            best = (score, image_path, label_path, gauze[:10])
    if best is None:
        raise SystemExit("No IGauze train tray with at least 10 cotton pieces and no hands")
    return best[1], best[3]


def _fill(arr, box):
    height, width = arr.shape[:2]
    x1, y1 = max(0, box["x"]), max(0, box["y"])
    x2 = min(width, box["x"] + box["w"])
    y2 = min(height, box["y"] + box["h"])
    pad = 8
    strips = []
    if y1 > pad:
        strips.append(arr[y1 - pad:y1, x1:x2])
    if y2 + pad < height:
        strips.append(arr[y2:y2 + pad, x1:x2])
    if x1 > pad:
        strips.append(arr[y1:y2, x1 - pad:x1])
    if x2 + pad < width:
        strips.append(arr[y1:y2, x2:x2 + pad])
    if not strips:
        return
    color = np.median(np.concatenate([strip.reshape(-1, 3) for strip in strips if strip.size]), axis=0)
    arr[y1:y2, x1:x2] = color


def _cotton_sprite(original, box):
    x, y, w, h = box["x"], box["y"], box["w"], box["h"]
    crop = np.array(original.crop((x, y, x + w, y + h)))
    red, green, blue = crop[:, :, 0], crop[:, :, 1], crop[:, :, 2]
    sponge = ((red > 145) & (green > 130) & (blue > 110) & (np.abs(red.astype(int) - green.astype(int)) < 55)) | (
        (red > 100) & (red > green + 22) & (red > blue + 22)
    )
    alpha = np.where(sponge, 255, 0).astype(np.uint8)
    if alpha.mean() < 40:
        alpha[:] = 255
    sprite = Image.fromarray(np.dstack([crop, alpha]), "RGBA")
    return sprite


def _tools(width):
    nano = ROOT / "nano"
    if str(nano) not in sys.path:
        sys.path.insert(0, str(nano))
    import compose_real
    import compose_trays

    hospi = Path(config.EXTERNAL_DIR) / "hospi" / "Hospi_Tools_small_Mask_RCNN"
    library = compose_trays._load_cutouts(
        hospi / "train", hospi / "train" / "1_Speciality_Train_Annotations.json"
    )
    chosen = []
    seen = set()
    target = max(72, int(width * 0.2))
    for spec in library:
        label = spec.get("label") or "instrument"
        if label in seen:
            continue
        cut = compose_real._tool_cutout(spec, target)
        if cut is None or cut.width < 24:
            continue
        seen.add(label)
        chosen.append((label, cut))
        if len(chosen) == 3:
            break
    if len(chosen) < 3:
        raise SystemExit("Need three instrument cutouts from HOSPI train")
    return chosen


def _place_tools(base, tools, count):
    spots = [
        (18, base.height - 18),
        (base.width - 18, base.height - 18),
        (base.width // 2, 18),
    ]
    placed = []
    for index, (label, cut) in enumerate(tools[:count]):
        anchor_x, anchor_y = spots[index]
        if index == 2:
            x = anchor_x - cut.width // 2
            y = anchor_y
        elif index == 0:
            x = anchor_x
            y = anchor_y - cut.height
        else:
            x = anchor_x - cut.width
            y = anchor_y - cut.height
        x = max(0, min(x, base.width - cut.width))
        y = max(0, min(y, base.height - cut.height))
        base.paste(cut, (x, y), cut)
        placed.append(label)
    return placed


def _frames(lines, tag, bare, sprites, tools):
    FRAMES.mkdir(parents=True, exist_ok=True)
    names = []
    for index, line in enumerate(lines):
        frame = bare.copy()
        for sprite, box in sprites[: line["sponges"]]:
            frame.paste(sprite, (box["x"], box["y"]), sprite)
        labels = _place_tools(frame, tools, line["tools"])
        name = f"{tag}_{index:02d}.jpg"
        frame.convert("RGB").save(FRAMES / name, quality=90)
        line["frame"] = name
        line["tool_names"] = labels
        names.append(name)
    return names


def _write_video(tag, names, slot):
    import cv2

    VIDEOS.mkdir(parents=True, exist_ok=True)
    first = cv2.imread(str(FRAMES / names[0]))
    height, width = first.shape[:2]
    fps = 4
    path = VIDEOS / f"{tag}.mp4"
    writer = cv2.VideoWriter(str(path), cv2.VideoWriter_fourcc(*"mp4v"), fps, (width, height))
    hold = max(1, int(round(slot * fps)))
    for name in names:
        image = cv2.imread(str(FRAMES / name))
        for _ in range(hold):
            writer.write(image)
    writer.release()
    return path.name


def _speak(cases):
    clips = DIR / "clips"
    clips.mkdir(parents=True, exist_ok=True)
    for path in clips.glob("*.wav"):
        path.unlink()
    jobs = []
    for case in cases:
        for index, line in enumerate(case["lines"]):
            dest = clips / f"{case['id']}_{index:02d}.wav"
            jobs.append({"wav": str(dest), "text": line["text"]})
    manifest = DIR / "speak.json"
    manifest.write_text(json.dumps(jobs), encoding="utf-8")
    script = DIR / "speak.ps1"
    script.write_text(
        "\n".join([
            "Add-Type -AssemblyName System.Speech",
            "$jobs = Get-Content -Raw -Encoding UTF8 '" + str(manifest) + "' | ConvertFrom-Json",
            "$synth = New-Object System.Speech.Synthesis.SpeechSynthesizer",
            "$synth.Rate = 0",
            "foreach ($job in $jobs) {",
            "  $synth.SetOutputToWaveFile($job.wav)",
            "  $synth.Speak($job.text)",
            "}",
            "$synth.Dispose()",
            "Write-Output 'spoke'",
        ]),
        encoding="utf-8",
    )
    import subprocess
    subprocess.check_call(["powershell", "-NoProfile", "-File", str(script)])
    return clips


def _slot(clips, cases):
    longest = 1.0
    for case in cases:
        for index in range(len(case["lines"])):
            with wave.open(str(clips / f"{case['id']}_{index:02d}.wav")) as handle:
                longest = max(longest, handle.getnframes() / handle.getframerate())
    return round(longest + 0.45, 2)


def _join(clips, case):
    AUDIO.mkdir(parents=True, exist_ok=True)
    paths = [clips / f"{case['id']}_{index:02d}.wav" for index in range(len(case["lines"]))]
    with wave.open(str(paths[0])) as handle:
        rate = handle.getframerate()
        width = handle.getsampwidth()
        channels = handle.getnchannels()
        params = handle.getparams()
    slot_frames = int(case["slot"] * rate)
    unit = width * channels
    blank = b"\x00" * unit
    payload = []
    for path in paths:
        with wave.open(str(path)) as handle:
            data = handle.readframes(handle.getnframes())
        have = len(data) // unit
        if have > slot_frames:
            data = data[: slot_frames * unit]
        else:
            data += blank * (slot_frames - have)
        payload.append(data)
    dest = AUDIO / case["audio"]
    with wave.open(str(dest), "w") as handle:
        handle.setparams(params)
        handle.writeframes(b"".join(payload))
    return dest


def build():
    image_path, gauze = _pick_tray()
    original = Image.open(image_path).convert("RGB")
    bare_arr = np.array(original)
    for box in gauze:
        _fill(bare_arr, box)
    bare = Image.fromarray(bare_arr).convert("RGBA")
    sprites = [(_cotton_sprite(original, box), box) for box in gauze]
    tools = _tools(original.width)
    cases = []
    for positive in (True, False):
        outcome = "positive" if positive else "negative"
        lines = _script(positive)
        _frames(lines, outcome, bare, sprites, tools)
        cases.append({
            "id": f"appendectomy_{outcome}",
            "procedure": "appendectomy",
            "title": "Appendectomy",
            "outcome": outcome,
            "expect": "SAFE" if positive else "BLOCK",
            "audio": f"appendectomy_{outcome}.wav",
            "video": f"{outcome}.mp4",
            "tray": image_path.name,
            "lines": lines,
        })
    clips = _speak(cases)
    slot = _slot(clips, cases)
    for case in cases:
        case["slot"] = slot
        case["duration"] = round(len(case["lines"]) * slot, 1)
        for index, line in enumerate(case["lines"]):
            line["t"] = round(index * slot, 1)
        _join(clips, case)
        names = [line["frame"] for line in case["lines"]]
        _write_video(case["outcome"], names, slot)
        print("case", case["id"], case["duration"], flush=True)
    DIR.mkdir(parents=True, exist_ok=True)
    CATALOG.write_text(json.dumps({
        "procedure": "Appendectomy",
        "tray": cases[0]["tray"],
        "slot": slot,
        "cases": cases,
    }, indent=1), encoding="utf-8")
    return cases


def load():
    if not CATALOG.is_file():
        build()
    return json.loads(CATALOG.read_text(encoding="utf-8"))


def case_by_id(case_id):
    for case in load()["cases"]:
        if case["id"] == case_id:
            return case
    return None
