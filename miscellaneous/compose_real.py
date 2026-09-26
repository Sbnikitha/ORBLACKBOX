"""Paste real HOSPI instruments onto real IGauze tray photos.

Train images use the IGauze train split and HOSPI train outlines.
Test images use the IGauze valid split and HOSPI val outlines.
The original test folders of both datasets are never opened.
"""
import argparse
import json
import random
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter

sys.path.insert(0, str(Path(__file__).resolve().parent))
import compose_trays

QUESTION = (
    "How many gauze pieces are on this tray, and which instruments are present? "
    "Reply with the gauze count, then the instrument names."
)
GAUZE = "gauze"
HAND = "hand"


def _class_names(root):
    yaml_path = next(Path(root).rglob("data.yaml"), None)
    if yaml_path is None:
        return {}
    names = {}
    lines = yaml_path.read_text(encoding="utf-8", errors="replace").splitlines()
    in_names = False
    for line in lines:
        if line.startswith("names:"):
            in_names = True
            rest = line.split(":", 1)[1].strip()
            if rest.startswith("[") and rest.endswith("]"):
                for index, name in enumerate(rest.strip("[]").split(",")):
                    names[index] = name.strip().strip("'\"")
                in_names = False
            continue
        if in_names:
            if not line.startswith(" ") and not line.startswith("-"):
                break
            if ":" in line:
                key, value = line.split(":", 1)
                names[int(key.strip())] = value.strip().strip("'\"")
    return names


def _kind(name):
    text = name.lower()
    if GAUZE in text:
        return "gauze"
    if HAND in text:
        return "hand"
    return "other"


def _splits(root):
    found = {}
    for labels in Path(root).rglob("*.txt"):
        if labels.name == "classes.txt":
            continue
        split = "train"
        for part in labels.parts:
            if part in ("valid", "val"):
                split = "test"
            elif part == "test":
                split = "skip"
            elif part == "train":
                split = "train"
        if split == "skip":
            continue
        images = labels.parent
        if images.name == "labels":
            images = images.parent / "images"
        image = None
        for suffix in (".jpg", ".jpeg", ".png"):
            candidate = images / (labels.stem + suffix)
            if candidate.is_file():
                image = candidate
                break
        if image is not None:
            found.setdefault(split, []).append((image, labels))
    return found


def _boxes(label_path, names, width, height):
    boxes = []
    for line in Path(label_path).read_text(encoding="utf-8", errors="replace").splitlines():
        parts = line.split()
        if len(parts) < 5:
            continue
        kind = _kind(names.get(int(parts[0]), "gauze"))
        if kind == "other":
            continue
        cx, cy, bw, bh = (float(parts[1]), float(parts[2]), float(parts[3]), float(parts[4]))
        w, h = bw * width, bh * height
        boxes.append({
            "x": int((cx - bw / 2) * width),
            "y": int((cy - bh / 2) * height),
            "w": max(1, int(w)),
            "h": max(1, int(h)),
            "kind": kind,
            "label": names.get(int(parts[0]), kind),
        })
    return boxes


def _tool_cutout(spec, target):
    import numpy as np

    image = Image.open(spec["path"]).convert("RGBA")
    mask = Image.new("L", image.size, 0)
    draw = ImageDraw.Draw(mask)
    for polygon in spec["polygons"]:
        draw.polygon(polygon, fill=255)
    image.putalpha(mask)
    bbox = mask.getbbox()
    if not bbox:
        return None
    crop = np.array(image.crop(bbox))
    rgb = crop[:, :, :3].astype(np.int16)
    height, width = rgb.shape[:2]
    edge = max(2, min(height, width) // 12)
    samples = np.concatenate([
        rgb[:edge, :].reshape(-1, 3),
        rgb[-edge:, :].reshape(-1, 3),
        rgb[:, :edge].reshape(-1, 3),
        rgb[:, -edge:].reshape(-1, 3),
    ])
    background = np.median(samples, axis=0)
    distance = np.abs(rgb - background).sum(axis=2)
    luma = rgb.mean(axis=2)
    sat = rgb.max(axis=2) - rgb.min(axis=2)
    drop = (distance < 42) | ((luma > 165) & (sat < 28))
    crop[:, :, 3] = np.where(drop, 0, crop[:, :, 3])
    cut = Image.fromarray(crop)
    tight = cut.getchannel("A").getbbox()
    if tight is None:
        return None
    cut = cut.crop(tight)
    scale = target / max(cut.size)
    size = (max(8, int(cut.width * scale)), max(8, int(cut.height * scale)))
    return cut.resize(size, Image.Resampling.BILINEAR)


def _lay_under_sponges(cut, gauze, width, height, rng):
    host = rng.choice(gauze)
    ox = host["x"] + host["w"] // 2 - cut.width // 2
    oy = host["y"] + host["h"] // 2 - cut.height // 2
    ox += rng.randint(-host["w"] // 2, max(1, host["w"] // 2))
    oy += rng.randint(-host["h"] // 3, max(1, host["h"] // 3))
    ox = max(0, min(ox, max(0, width - cut.width)))
    oy = max(0, min(oy, max(0, height - cut.height)))
    return ox, oy


def _paste_tool(base, cut, x, y):
    alpha = cut.getchannel("A").filter(ImageFilter.GaussianBlur(1.2))
    cut.putalpha(alpha)
    shadow = Image.new("RGBA", cut.size, (0, 0, 0, 0))
    shadow.putalpha(alpha.point(lambda value: int(value * 0.4)))
    shadow = shadow.filter(ImageFilter.GaussianBlur(3))
    base.paste(shadow, (min(base.width - 1, x + 4), min(base.height - 1, y + 5)), shadow)
    base.paste(cut, (x, y), cut)


def _occluder(original, boxes):
    import numpy as np

    arr = np.asarray(original).astype(np.int16)
    height, width = arr.shape[:2]
    red, green, blue = arr[:, :, 0], arr[:, :, 1], arr[:, :, 2]
    sponge = ((red > 145) & (green > 130) & (blue > 110) & (np.abs(red - green) < 50)) | (
        (red > 100) & (red > green + 22) & (red > blue + 22)
    )
    skin = (red > 135) & (green > 100) & (blue > 70) & (red > blue + 15) & (np.abs(red - green) < 70)
    keep = np.zeros((height, width), dtype=bool)
    for box in boxes:
        x1, y1 = max(0, box["x"]), max(0, box["y"])
        x2 = min(width, box["x"] + box["w"])
        y2 = min(height, box["y"] + box["h"])
        if x2 <= x1 or y2 <= y1:
            continue
        region = sponge if box["kind"] == "gauze" else skin
        chosen = region[y1:y2, x1:x2]
        if chosen.mean() < 0.12:
            chosen = np.ones_like(chosen)
        keep[y1:y2, x1:x2] |= chosen
    mask = Image.fromarray(keep.astype(np.uint8) * 255, "L")
    mask = mask.filter(ImageFilter.MaxFilter(3))
    mask = mask.filter(ImageFilter.GaussianBlur(0.8))
    layer = original.convert("RGBA")
    layer.putalpha(mask)
    return layer


def _place_clear(cut, occupied, width, height, rng):
    for _ in range(40):
        x = rng.randint(0, max(1, width - cut.width))
        y = rng.randint(0, max(1, height - cut.height))
        if not compose_trays._overlaps((x, y, cut.width, cut.height), occupied):
            return x, y
    return None


def _compose(image_path, label_path, names, library, rng, dest, style="cover"):
    image = Image.open(image_path).convert("RGB")
    boxes = _boxes(label_path, names, image.width, image.height)
    gauze = [box for box in boxes if box["kind"] == "gauze"]
    hands = [box for box in boxes if box["kind"] == "hand"]
    if not gauze:
        return None
    original = image.copy()
    cover = _occluder(original, boxes) if style == "cover" else None
    occupied = list(boxes)
    instruments = []
    for spec in rng.sample(library, k=min(2, len(library))):
        if style == "previous":
            cut = compose_trays._rgba_cutout(spec, target=max(48, int(image.width * 0.18)))
            if cut is None or cut.width >= image.width or cut.height >= image.height:
                continue
            spot = _place_clear(cut, occupied + instruments, image.width, image.height, rng)
            if spot is None:
                continue
            x, y = spot
            image.paste(cut, (x, y), cut)
        else:
            host = rng.choice(gauze)
            target = int(max(host["w"], host["h"]) * rng.uniform(1.4, 2.1))
            cut = _tool_cutout(spec, target=max(36, target))
            if cut is None:
                continue
            cut = cut.rotate(rng.uniform(-28, 28), expand=True, resample=Image.Resampling.BICUBIC)
            if cut.width >= image.width or cut.height >= image.height:
                continue
            x, y = _lay_under_sponges(cut, gauze, image.width, image.height, rng)
            _paste_tool(image, cut, x, y)
        instruments.append({
            "x": x, "y": y, "w": cut.width, "h": cut.height,
            "kind": "instrument", "label": spec["label"], "source": spec["path"],
        })
    if not instruments:
        return None
    if cover is not None:
        image.paste(cover, (0, 0), cover)
    dest.parent.mkdir(parents=True, exist_ok=True)
    image.save(dest, quality=92)
    names_text = ", ".join(item["label"] for item in instruments)
    gauze_count = len(gauze)
    gauze_word = "gauze" if gauze_count == 1 else "gauze pieces"
    record = {
        "image": str(dest.resolve()),
        "background": str(image_path),
        "width": image.width,
        "height": image.height,
        "gauze": gauze,
        "hands": hands,
        "instruments": instruments,
        "gauze_count": gauze_count,
        "question": QUESTION,
        "answer": f"{gauze_count} {gauze_word}. Instruments: {names_text}.",
    }
    dest.with_suffix(".json").write_text(json.dumps(record), encoding="utf-8")
    return record


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--igauze", default="data/external/igauze")
    parser.add_argument("--hospi", default="data/external/hospi/Hospi_Tools_small_Mask_RCNN")
    parser.add_argument("--out", default="data/composites_real")
    parser.add_argument("--train-n", type=int, default=80)
    parser.add_argument("--test-n", type=int, default=20)
    parser.add_argument("--style", choices=("cover", "previous"), default="cover")
    args = parser.parse_args()
    igauze = Path(args.igauze)
    if not igauze.is_dir():
        raise SystemExit(
            "IGauze photos are not in this project. Download IGauze CZ (YOLOv8) from "
            "https://universe.roboflow.com/ntu-edf5y/igauze-cz and unzip it to "
            f"{igauze}. HOSPI is already here. This script does not need an API key in chat."
        )
    hospi = Path(args.hospi)
    train_lib = compose_trays._load_cutouts(
        hospi / "train", hospi / "train" / "1_Speciality_Train_Annotations.json")
    val_lib = compose_trays._load_cutouts(
        hospi / "val", hospi / "val" / "1_Speciality_Val_Annotations.json")
    photos = _splits(igauze)
    if not photos.get("train"):
        raise SystemExit(f"No IGauze train images found under {igauze}")
    names = _class_names(igauze)
    print(
        f"igauze train {len(photos['train'])} valid {len(photos.get('test', []))} "
        f"hospi train cutouts {len(train_lib)} val cutouts {len(val_lib)}",
        flush=True,
    )
    rng = random.Random(11)
    out = Path(args.out)
    plan = [("train", photos["train"], train_lib, args.train_n)]
    if photos.get("test") and val_lib:
        plan.append(("test", photos["test"], val_lib, args.test_n))
    for split, pairs, library, limit in plan:
        rng.shuffle(pairs)
        written = []
        for image_path, label_path in pairs:
            if len(written) >= limit:
                break
            record = _compose(
                image_path, label_path, names, library, rng,
                out / split / f"tray_{len(written):04d}.jpg",
                style=args.style,
            )
            if record:
                written.append(record)
        dest = out / f"{split}.jsonl"
        dest.parent.mkdir(parents=True, exist_ok=True)
        with open(dest, "w", encoding="utf-8") as handle:
            for row in written:
                handle.write(json.dumps({
                    "image": row["image"], "question": row["question"], "answer": row["answer"],
                }) + "\n")
        print(f"wrote {dest} lines {len(written)}", flush=True)


if __name__ == "__main__":
    main()
