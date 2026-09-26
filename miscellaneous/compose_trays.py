"""Paste real HOSPI instruments onto sponge trays.

Train composites use only the HOSPI train split.
Test composites use only the HOSPI val split.
The original HOSPI test images are never opened.
Demo tray files in data/photos are not overwritten.
"""
import argparse
import json
import os
import random
import sys
from pathlib import Path

from PIL import Image, ImageDraw

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "app"))
import photos

QUESTION = (
    "How many gauze sponges are on the tray, and which instruments were added? "
    "Reply with the sponge count, then the instrument names."
)


def _load_cutouts(split_dir, annotations):
    data = json.loads(Path(annotations).read_text(encoding="utf-8"))
    cutouts = []
    for item in data.values():
        name = item.get("filename")
        regions = item.get("regions") or []
        if not name or not regions:
            continue
        image_path = Path(split_dir) / name
        if not image_path.is_file():
            continue
        polygons = []
        label = "instrument"
        for region in regions:
            shape = region.get("shape_attributes") or {}
            if shape.get("name") != "polygon":
                continue
            xs = shape.get("all_points_x") or []
            ys = shape.get("all_points_y") or []
            if len(xs) < 3 or len(xs) != len(ys):
                continue
            polygons.append(list(zip(xs, ys)))
            label = (region.get("region_attributes") or {}).get("Component") or label
        if polygons:
            cutouts.append({
                "path": str(image_path),
                "polygons": polygons,
                "label": str(label).replace("-", " ").replace("_", " "),
            })
    return cutouts


def _rgba_cutout(spec, target=120):
    image = Image.open(spec["path"]).convert("RGBA")
    mask = Image.new("L", image.size, 0)
    draw = ImageDraw.Draw(mask)
    for polygon in spec["polygons"]:
        draw.polygon(polygon, fill=255)
    image.putalpha(mask)
    bbox = mask.getbbox()
    if not bbox:
        return None
    crop = image.crop(bbox)
    scale = target / max(crop.size)
    size = (max(8, int(crop.width * scale)), max(8, int(crop.height * scale)))
    return crop.resize(size, Image.Resampling.BILINEAR)


def _overlaps(box, boxes):
    x, y, w, h = box
    for other in boxes:
        ox, oy, ow, oh = other["x"], other["y"], other["w"], other["h"]
        ix = max(0, min(x + w, ox + ow) - max(x, ox))
        iy = max(0, min(y + h, oy + oh) - max(y, oy))
        if ix * iy > 0:
            return True
    return False


def _place(cut, sponge_boxes, rng):
    width, height = cut.size
    for _ in range(40):
        x = rng.randint(48, max(49, 600 - width))
        y = rng.randint(300, max(301, 450 - height))
        box = (x, y, width, height)
        if not _overlaps(box, sponge_boxes):
            return x, y
    return None


def _compose(count, variant, library, rng, dest_image):
    image, _marks = photos._draw(count, variant, with_tools=False)
    dest_image.parent.mkdir(parents=True, exist_ok=True)
    image.save(dest_image, quality=92)
    sponge_boxes = [
        box for box in photos.analyze(str(dest_image))["boxes"] if box.get("kind") == "sponge"
    ]
    chosen = rng.sample(library, k=min(2, len(library)))
    instruments = []
    for spec in chosen:
        cut = _rgba_cutout(spec)
        if cut is None:
            continue
        spot = _place(cut, sponge_boxes + instruments, rng)
        if spot is None:
            continue
        x, y = spot
        image.paste(cut, (x, y), cut)
        instruments.append({
            "x": x, "y": y, "w": cut.width, "h": cut.height,
            "kind": "instrument", "label": spec["label"],
            "source": spec["path"],
        })
    image.save(dest_image, quality=92)
    names = ", ".join(item["label"] for item in instruments) or "none"
    sponge_count = len(sponge_boxes)
    sponge_word = "sponge" if sponge_count == 1 else "sponges"
    record = {
        "image": str(dest_image.resolve()),
        "sponges": sponge_boxes,
        "instruments": instruments,
        "sponge_count": sponge_count,
        "question": QUESTION,
        "answer": f"{sponge_count} {sponge_word}. Instruments: {names}.",
    }
    dest_image.with_suffix(".json").write_text(json.dumps(record), encoding="utf-8")
    return record


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--hospi", required=True)
    parser.add_argument("--out", default="data/composites")
    parser.add_argument("--train-n", type=int, default=64)
    parser.add_argument("--test-n", type=int, default=16)
    args = parser.parse_args()
    root = Path(args.hospi)
    train_lib = _load_cutouts(root / "train", root / "train" / "1_Speciality_Train_Annotations.json")
    val_lib = _load_cutouts(root / "val", root / "val" / "1_Speciality_Val_Annotations.json")
    if not train_lib or not val_lib:
        raise SystemExit(f"Need train and val outlines under {root}")
    print(f"train cutouts {len(train_lib)} val cutouts {len(val_lib)} test images left untouched", flush=True)
    out = Path(args.out)
    rng = random.Random(11)
    written = {"train": [], "test": []}
    for index in range(args.train_n):
        record = _compose(index % 16, 80 + index, train_lib, rng, out / "train" / f"tray_{index:04d}.jpg")
        written["train"].append(record)
        if index % 16 == 15:
            print(f"train {index + 1}/{args.train_n}", flush=True)
    for index in range(args.test_n):
        record = _compose(index % 16, 400 + index, val_lib, rng, out / "test" / f"tray_{index:04d}.jpg")
        written["test"].append(record)
    for split, rows in written.items():
        dest = out / f"{split}.jsonl"
        with open(dest, "w", encoding="utf-8") as handle:
            for row in rows:
                handle.write(json.dumps({
                    "image": row["image"], "question": row["question"], "answer": row["answer"],
                }) + "\n")
        print(f"wrote {dest} lines {len(rows)}", flush=True)


if __name__ == "__main__":
    main()
