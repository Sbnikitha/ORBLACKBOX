"""Turn the real photo folders into the layout YOLO training expects.

Real combined trays live here, image and json side by side:

    data/composites_real/train/tray_0000.jpg
    data/composites_real/train/tray_0000.json
    data/composites_real/test/...

YOLO needs:

    data/yolo/combined_new/train/images
    data/yolo/combined_new/train/labels
    data/yolo/combined_new/valid/images
    data/yolo/combined_new/valid/labels
    data/yolo/combined_new/data.yaml

IGauze is already train/images and train/labels, but its data.yaml
points at ../train/images, one folder too high. HOSPI uses images/train.
"""
import json
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CLASSES = ["gauze", "red_gauze", "stained_gauze", "hand", "stained_hand", "instrument"]


def _class_id(label):
    text = str(label).lower().replace(" ", "").replace("_", "")
    if "stainedhand" in text:
        return 4
    if text == "hand":
        return 3
    if "stained" in text:
        return 2
    if "red" in text:
        return 1
    return 0


def _yolo_box(box, width, height, class_id):
    bw = max(1.0, float(box["w"])) / width
    bh = max(1.0, float(box["h"])) / height
    cx = (float(box["x"]) + float(box["w"]) / 2) / width
    cy = (float(box["y"]) + float(box["h"]) / 2) / height
    cx = min(0.999, max(0.001, cx))
    cy = min(0.999, max(0.001, cy))
    bw = min(0.999, max(0.001, bw))
    bh = min(0.999, max(0.001, bh))
    return f"{class_id} {cx:.6f} {cy:.6f} {bw:.6f} {bh:.6f}"


def _link(src, dest):
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.exists():
        return
    try:
        os.link(src, dest)
    except OSError:
        dest.write_bytes(src.read_bytes())


def _lines(image_path, record):
    width = record.get("width")
    height = record.get("height")
    if not width or not height:
        from PIL import Image
        with Image.open(image_path) as image:
            width, height = image.size
    lines = []
    for box in record.get("gauze") or []:
        lines.append(_yolo_box(box, width, height, _class_id(box.get("label", "gauze"))))
    for box in record.get("hands") or []:
        lines.append(_yolo_box(box, width, height, _class_id(box.get("label", "hand"))))
    for box in record.get("instruments") or []:
        lines.append(_yolo_box(box, width, height, 5))
    return lines


def prepare_combined(source, dest):
    """source has train/ and test/ with jpg+json. dest becomes a YOLO dataset."""
    source = Path(source)
    dest = Path(dest)
    mapping = {"train": "train", "test": "valid"}
    counts = {}
    for split, arc in mapping.items():
        folder = source / split
        images = dest / arc / "images"
        labels = dest / arc / "labels"
        images.mkdir(parents=True, exist_ok=True)
        labels.mkdir(parents=True, exist_ok=True)
        n = 0
        if not folder.is_dir():
            counts[arc] = 0
            continue
        for image_path in sorted(folder.glob("*.jpg")):
            side = image_path.with_suffix(".json")
            if not side.is_file():
                continue
            record = json.loads(side.read_text(encoding="utf-8"))
            _link(image_path, images / image_path.name)
            (labels / f"{image_path.stem}.txt").write_text(
                "\n".join(_lines(image_path, record)) + "\n", encoding="utf-8")
            n += 1
        counts[arc] = n
    if counts.get("train", 0) == 0:
        raise SystemExit(f"No tray photos in {source / 'train'}")
    names = "\n".join(f"  {i}: {name}" for i, name in enumerate(CLASSES))
    yaml = (
        f"path: {dest.resolve().as_posix()}\n"
        "train: train/images\n"
        "val: valid/images\n"
        f"names:\n{names}\n"
    )
    (dest / "data.yaml").write_text(yaml, encoding="utf-8")
    print(f"YOLO layout {dest} train {counts['train']} valid {counts.get('valid', 0)}", flush=True)
    return dest / "data.yaml"


def combined_yaml(previous=False):
    name = "combined_previous" if previous else "combined_new"
    unzipped = Path(name) / "data.yaml"
    images = Path(name) / "train" / "images"
    if unzipped.is_file() and images.is_dir() and any(images.glob("*.jpg")):
        return unzipped
    source = ROOT / "data" / ("composites_previous" if previous else "composites_real")
    if not source.is_dir():
        raise SystemExit(
            f"Real trays are not in {source}. Expected {source / 'train'} with jpg and json files."
        )
    return prepare_combined(source, ROOT / "data" / "yolo" / name)


def igauze_yaml():
    candidates = [
        ROOT / "data" / "external" / "igauze",
        Path("igauze"),
    ]
    root = next((path for path in candidates if (path / "train" / "images").is_dir()), None)
    if root is None:
        raise SystemExit("IGauze train/images was not found under data/external/igauze or ./igauze")
    names = ["Gauze", "Hand", "RedGauze", "StainedGauze", "StainedHand", "gauze"]
    body = "\n".join(f"  {i}: {name}" for i, name in enumerate(names))
    text = (
        f"path: {root.resolve().as_posix()}\n"
        "train: train/images\n"
        "val: valid/images\n"
        "test: test/images\n"
        f"names:\n{body}\n"
    )
    dest = root / "sentinel.yaml"
    dest.write_text(text, encoding="utf-8")
    print(f"IGauze yaml {dest} (real folders are train/images, not ../train/images)", flush=True)
    return dest


def hospi_yaml():
    candidates = [
        ROOT / "data" / "external" / "hospi" / "HOSPI_Tools_small_yolov5",
        Path("hospi_yolo"),
    ]
    root = next((path for path in candidates if (path / "images" / "train").is_dir()), None)
    if root is None:
        raise SystemExit("HOSPI images/train was not found.")
    highest = 0
    label_root = root / "labels"
    if label_root.is_dir():
        for path in label_root.rglob("*.txt"):
            if path.name.endswith(".cache"):
                continue
            for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
                parts = line.split()
                if parts and parts[0].isdigit():
                    highest = max(highest, int(parts[0]))
    names = "\n".join(f"  {i}: tool_{i}" for i in range(highest + 1))
    text = (
        f"path: {root.resolve().as_posix()}\n"
        "train: images/train\n"
        "val: images/val\n"
        "test: images/test\n"
        f"names:\n{names}\n"
    )
    dest = root / "sentinel.yaml"
    dest.write_text(text, encoding="utf-8")
    print(f"HOSPI yaml {dest} (real folders are images/train and labels/train)", flush=True)
    return dest
