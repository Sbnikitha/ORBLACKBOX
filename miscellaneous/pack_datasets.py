"""Zip IGauze, HOSPI, and both combined object-detection sets."""
import json
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = Path.home() / "Desktop" / "OR_Sentinel_datasets.zip"
CLASSES = ["gauze", "red_gauze", "stained_gauze", "hand", "stained_hand", "instrument"]


def _yaml(names, train, val, test=None):
    lines = [f"train: {train}", f"val: {val}"]
    if test:
        lines.append(f"test: {test}")
    lines.append("names:")
    for index, name in enumerate(names):
        lines.append(f"  {index}: {name}")
    return "\n".join(lines) + "\n"


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
    bw = max(1, box["w"]) / width
    bh = max(1, box["h"]) / height
    cx = (box["x"] + box["w"] / 2) / width
    cy = (box["y"] + box["h"] / 2) / height
    cx = min(0.999, max(0.001, cx))
    cy = min(0.999, max(0.001, cy))
    bw = min(0.999, max(0.001, bw))
    bh = min(0.999, max(0.001, bh))
    return f"{class_id} {cx:.6f} {cy:.6f} {bw:.6f} {bh:.6f}"


def _add_tree(archive, source, arc_root, count, skip=()):
    skipped = {name.lower() for name in skip}
    for path in source.rglob("*"):
        if not path.is_file():
            continue
        if path.name.lower() in skipped:
            continue
        if path.suffix.lower() in {".cache"} or path.name.endswith(".cache"):
            continue
        archive.write(path, f"{arc_root}/{path.relative_to(source).as_posix()}")
        count[0] += 1
        if count[0] % 4000 == 0:
            print(f"zipped {count[0]} files", flush=True)


def _add_combined(archive, source, arc_root, count):
    from PIL import Image

    names = _yaml(CLASSES, "train/images", "valid/images")
    archive.writestr(f"{arc_root}/data.yaml", names)
    split_name = {"train": "train", "test": "valid"}
    for split, arc_split in split_name.items():
        folder = source / split
        if not folder.is_dir():
            continue
        for image_path in sorted(folder.glob("tray_*.jpg")):
            record = json.loads(image_path.with_suffix(".json").read_text(encoding="utf-8"))
            width = record.get("width")
            height = record.get("height")
            if not width or not height:
                with Image.open(image_path) as image:
                    width, height = image.size
            lines = []
            for box in record.get("gauze") or []:
                lines.append(_yolo_box(box, width, height, _class_id(box.get("label", "gauze"))))
            for box in record.get("hands") or []:
                lines.append(_yolo_box(box, width, height, _class_id(box.get("label", "hand"))))
            for box in record.get("instruments") or []:
                lines.append(_yolo_box(box, width, height, 5))
            stem = image_path.stem
            archive.write(image_path, f"{arc_root}/{arc_split}/images/{stem}.jpg")
            archive.writestr(f"{arc_root}/{arc_split}/labels/{stem}.txt", "\n".join(lines) + "\n")
            count[0] += 1
            if count[0] % 2000 == 0:
                print(f"zipped {count[0]} files", flush=True)


def _hospi_names(label_root):
    highest = 0
    for path in label_root.rglob("*.txt"):
        for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
            parts = line.split()
            if parts and parts[0].isdigit():
                highest = max(highest, int(parts[0]))
    return [f"tool_{index}" for index in range(highest + 1)]


def main():
    previous = ROOT / "data" / "composites_previous"
    current = ROOT / "data" / "composites_real"
    if not previous.is_dir() or not current.is_dir():
        raise SystemExit("Combined image folders are missing.")
    OUT.parent.mkdir(parents=True, exist_ok=True)
    if OUT.exists():
        OUT.unlink()
    count = [0]
    with zipfile.ZipFile(OUT, "w", compression=zipfile.ZIP_STORED, allowZip64=True) as archive:
        for script in ("nano_train.py", "later_igauze.py", "later_hospi.py"):
            archive.write(ROOT / "nano" / script, script)
        igauze_yaml = _yaml(
            ["Gauze", "Hand", "RedGauze", "StainedGauze", "StainedHand", "gauze"],
            "train/images", "valid/images", "test/images",
        )
        archive.writestr("igauze/data.yaml", igauze_yaml)
        _add_tree(archive, ROOT / "data" / "external" / "igauze", "igauze", count, skip={"data.yaml"})
        hospi = ROOT / "data" / "external" / "hospi" / "HOSPI_Tools_small_yolov5"
        archive.writestr(
            "hospi_yolo/data.yaml",
            _yaml(_hospi_names(hospi / "labels"), "images/train", "images/val", "images/test"),
        )
        _add_tree(archive, hospi, "hospi_yolo", count)
        _add_tree(
            archive,
            ROOT / "data" / "external" / "hospi" / "Hospi_Tools_small_Mask_RCNN",
            "hospi_masks",
            count,
        )
        _add_combined(archive, previous, "combined_previous", count)
        _add_combined(archive, current, "combined_new", count)
    print(f"wrote {OUT} files {count[0]} bytes {OUT.stat().st_size}", flush=True)


if __name__ == "__main__":
    main()
