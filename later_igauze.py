"""Train later: IGauze only, gauze and hands.

Unzip OR_Sentinel_datasets.zip and run this from that folder:

    pip install ultralytics
    python later_igauze.py
"""
import argparse
from pathlib import Path


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--data", default="igauze/data.yaml")
    parser.add_argument("--model", default="yolov8s.pt")
    parser.add_argument("--epochs", type=int, default=40)
    parser.add_argument("--imgsz", type=int, default=640)
    parser.add_argument("--batch", type=int, default=16)
    args = parser.parse_args()
    data = Path(args.data)
    if not data.is_file():
        raise SystemExit(f"Missing {data}. Unzip the bundle and run this script from that folder.")
    from ultralytics import YOLO

    YOLO(args.model).train(
        data=str(data.resolve()),
        epochs=args.epochs,
        imgsz=args.imgsz,
        batch=args.batch,
        project="runs",
        name="igauze",
        exist_ok=True,
    )


if __name__ == "__main__":
    main()
