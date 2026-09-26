"""Run the real detector on one tray photo.

Paste this nano folder onto the Nano, then:

    pip install ultralytics
    python infer.py path/to/tray.jpg

Weight: weights/detector.pt
Training script: nano_train.py
Dataset: IGauze CZ tray photos with HOSPI instruments laid under the cotton.
That combined set is data/composites_real (7,201 train, 341 valid).
Classes: gauze, red_gauze, stained_gauze, hand, stained_hand, instrument.
"""
import sys
from collections import Counter
from pathlib import Path

WEIGHT = Path(__file__).resolve().parent / "weights" / "detector.pt"
NAMES = ["gauze", "red_gauze", "stained_gauze", "hand", "stained_hand", "instrument"]


def main():
    if len(sys.argv) < 2:
        raise SystemExit("usage: python infer.py path/to/tray.jpg")
    image = Path(sys.argv[1])
    if not WEIGHT.is_file():
        raise SystemExit(f"Missing {WEIGHT}. Copy weights/detector.pt with this folder.")
    from ultralytics import YOLO

    result = YOLO(str(WEIGHT)).predict(str(image), imgsz=640, verbose=False)[0]
    counts = Counter()
    for box in result.boxes:
        name = NAMES[int(box.cls)]
        counts[name] += 1
        x1, y1, x2, y2 = [round(float(v), 1) for v in box.xyxy[0]]
        print(f"{name} {float(box.conf):.2f} box {x1} {y1} {x2} {y2}")
    cotton = counts["gauze"] + counts["red_gauze"] + counts["stained_gauze"]
    print(f"cotton {cotton} tools {counts['instrument']} hands {counts['hand'] + counts['stained_hand']}")


if __name__ == "__main__":
    main()
