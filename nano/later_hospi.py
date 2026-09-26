"""Train later: HOSPI instruments only.

    pip install ultralytics
    python nano/later_hospi.py

Uses data/external/hospi/HOSPI_Tools_small_yolov5/images/train
and the matching labels/train folder.
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import yolo_layout


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--data", default="")
    parser.add_argument("--model", default="yolov8s.pt")
    parser.add_argument("--epochs", type=int, default=40)
    parser.add_argument("--imgsz", type=int, default=640)
    parser.add_argument("--batch", type=int, default=16)
    args = parser.parse_args()
    data = Path(args.data) if args.data else yolo_layout.hospi_yaml()
    if not data.is_file():
        raise SystemExit(f"Missing {data}")
    from ultralytics import YOLO

    YOLO(args.model).train(
        data=str(data.resolve()),
        epochs=args.epochs,
        imgsz=args.imgsz,
        batch=args.batch,
        project="runs",
        name="hospi",
        exist_ok=True,
    )


if __name__ == "__main__":
    main()
