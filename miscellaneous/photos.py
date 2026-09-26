"""Synthetic tray photos and a real blob counter. Filenames are <count>_<letter>.jpg."""
import glob
import json
import os
import random
from pathlib import Path

from PIL import Image, ImageChops, ImageDraw, ImageEnhance, ImageFilter

import config

_CACHE = {}


_RENDER = "or-cam-v3"


def ensure():
    os.makedirs(config.PHOTO_DIR, exist_ok=True)
    marker = os.path.join(config.PHOTO_DIR, ".render")
    ready = os.path.exists(os.path.join(config.PHOTO_DIR, "15_b.jpg"))
    if ready and os.path.exists(marker) and open(marker, encoding="utf-8").read().strip() == _RENDER:
        return config.PHOTO_DIR
    for path in glob.glob(os.path.join(config.PHOTO_DIR, "*")):
        if path.endswith((".jpg", ".tools.json")):
            os.remove(path)
    _CACHE.clear()
    for count in range(16):
        for variant, letter in enumerate("ab"):
            path = os.path.join(config.PHOTO_DIR, f"{count:02d}_{letter}.jpg")
            image, tools = _draw(count, variant)
            image.save(path, quality=92)
            with open(path.replace(".jpg", ".tools.json"), "w", encoding="utf-8") as handle:
                json.dump(tools, handle)
    with open(marker, "w", encoding="utf-8") as handle:
        handle.write(_RENDER)
    return config.PHOTO_DIR


def _gauze(draw, x, y, width, height, rng):
    draw.ellipse([x + 10, y + height - 6, x + width - 6, y + height + 14], fill=(10, 16, 16))
    body = (236, 230, 214) if rng.random() > 0.3 else (228, 220, 204)
    draw.rounded_rectangle([x, y, x + width, y + height], radius=12, fill=body)
    draw.rounded_rectangle([x + 8, y + 5, x + width - 10, y + height // 2 + 4], radius=8, fill=(246, 241, 228))
    fold = y + height // 2
    draw.polygon([(x + 4, fold), (x + width - 4, fold - 6), (x + width - 4, fold + 8), (x + 4, fold + 10)], fill=(214, 206, 190))
    for line_y in range(y + 7, y + height - 5, 4):
        draw.line([(x + 5, line_y), (x + width - 5, line_y)], fill=(222, 216, 200), width=1)
    for line_x in range(x + 7, x + width - 5, 6):
        draw.line([(line_x, y + 5), (line_x + 2, y + height - 5)], fill=(230, 224, 208), width=1)
    if rng.random() > 0.35:
        stain_x = x + rng.randint(18, max(19, width // 2))
        stain_y = y + rng.randint(14, max(15, height // 2))
        draw.ellipse([stain_x, stain_y, stain_x + 28, stain_y + 18], fill=(132, 36, 34))
        draw.ellipse([stain_x + 6, stain_y + 4, stain_x + 16, stain_y + 12], fill=(168, 64, 58))


def _draw(count, variant, with_tools=True):
    rng = random.Random(2000 + count * 19 + variant)
    width, height = 640, 480
    image = Image.new("RGB", (width, height), (16, 34, 32))
    pixels = image.load()
    for y in range(height):
        for x in range(0, width, 2):
            fold = 10 if ((x // 36 + y // 28) % 2 == 0) else -4
            jitter = rng.randint(-5, 5)
            pixels[x, y] = (
                max(0, min(255, 20 + jitter)),
                max(0, min(255, 38 + fold + jitter)),
                max(0, min(255, 34 + jitter)),
            )
            if x + 1 < width:
                pixels[x + 1, y] = pixels[x, y]
    draw = ImageDraw.Draw(image)
    draw.rounded_rectangle([36, 28, 604, 452], radius=36, fill=(54, 58, 62), outline=(96, 102, 108), width=4)
    for y in range(48, 440, 3):
        shade = 70 + int(22 * (1 - abs(y - 240) / 220))
        draw.line([(58, y), (582, y)], fill=(shade, shade + 2, shade + 6))
    draw.ellipse([180, 90, 470, 250], fill=(118, 124, 128))
    draw.arc([70, 40, 250, 120], 200, 340, fill=(168, 174, 176), width=2)
    cols = 4
    for i in range(count):
        col = i % cols
        row = i // cols
        x = 78 + col * 132 + rng.randint(-3, 3)
        y = 78 + row * 86 + rng.randint(-2, 2)
        _gauze(draw, x, y, 100, 58, rng)
    vignette = Image.new("L", (width, height), 0)
    ImageDraw.Draw(vignette).ellipse([-20, -10, width + 20, height + 10], fill=210)
    ImageDraw.Draw(vignette).ellipse([70, 36, width - 70, height - 36], fill=255)
    vignette = vignette.filter(ImageFilter.GaussianBlur(28))
    dark = Image.new("RGB", (width, height), (6, 10, 12))
    image = Image.composite(image, dark, vignette)
    image = ImageEnhance.Color(image).enhance(0.78)
    image = ImageEnhance.Contrast(image).enhance(1.08)
    if not with_tools:
        return image, []
    draw = ImageDraw.Draw(image)
    tools = [
        (58, 412, 130, 18, "instrument", "scalpel", (96, 118, 148)),
        (210, 408, 100, 24, "instrument", "hemostat", (110, 128, 150)),
        (330, 410, 88, 20, "instrument", "forceps", (84, 108, 140)),
        (440, 416, 42, 8, "sharp", "needle", (196, 150, 64)),
        (500, 414, 28, 8, "sharp", "needle 2", (186, 120, 70)),
    ]
    marks = []
    for x, y, w, h, kind, label, color in tools:
        draw.rounded_rectangle([x, y, x + w, y + h], radius=3, fill=color)
        marks.append({"x": x, "y": y, "w": w, "h": h, "kind": kind, "label": label})
    return image, marks


def list_photos():
    ensure()
    rows = []
    for path in sorted(glob.glob(os.path.join(config.PHOTO_DIR, "*"))):
        if Path(path).suffix.lower() not in (".jpg", ".jpeg", ".png"):
            continue
        try:
            truth = int(Path(path).stem.split("_")[0])
        except ValueError:
            continue
        rows.append({"name": os.path.basename(path), "truth": truth})
    return rows


def analyze(path):
    """Count sponges and return a box around each one."""
    path = str(path)
    stamp = os.path.getmtime(path) if os.path.exists(path) else 0
    key = (path, stamp)
    if key in _CACHE:
        return _CACHE[key]
    image = Image.open(path).convert("RGB")
    width, height = image.size
    raw = image.tobytes()
    bright = bytearray(width * height)
    for i in range(width * height):
        red, green, blue = raw[i * 3], raw[i * 3 + 1], raw[i * 3 + 2]
        bright[i] = 1 if red > 185 and green > 150 and blue > 130 else 0
    seen = bytearray(width * height)
    found = 0
    boxes = []
    for idx in range(width * height):
        if not bright[idx] or seen[idx]:
            continue
        stack = [idx]
        seen[idx] = 1
        size = 0
        min_x = max_x = idx % width
        min_y = max_y = idx // width
        while stack:
            cur = stack.pop()
            size += 1
            x = cur % width
            y = cur // width
            min_x = min(min_x, x)
            max_x = max(max_x, x)
            min_y = min(min_y, y)
            max_y = max(max_y, y)
            if x > 0:
                nxt = cur - 1
                if bright[nxt] and not seen[nxt]:
                    seen[nxt] = 1
                    stack.append(nxt)
            if x + 1 < width:
                nxt = cur + 1
                if bright[nxt] and not seen[nxt]:
                    seen[nxt] = 1
                    stack.append(nxt)
            if cur >= width:
                nxt = cur - width
                if bright[nxt] and not seen[nxt]:
                    seen[nxt] = 1
                    stack.append(nxt)
            if cur + width < width * height:
                nxt = cur + width
                if bright[nxt] and not seen[nxt]:
                    seen[nxt] = 1
                    stack.append(nxt)
        if size > 80:
            found += 1
            boxes.append({
                "x": min_x, "y": min_y,
                "w": max_x - min_x + 1, "h": max_y - min_y + 1,
                "label": f"sponge {found}",
                "kind": "sponge",
            })
    side = str(path).replace(".jpg", ".tools.json").replace(".jpeg", ".tools.json").replace(".png", ".tools.json")
    if os.path.exists(side):
        with open(side, encoding="utf-8") as handle:
            boxes.extend(json.load(handle))
    result = {"count": found, "boxes": boxes, "width": width, "height": height}
    _CACHE[key] = result
    return result


def count_image(path):
    return analyze(path)["count"]
