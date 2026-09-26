"""Train on the real combined trays: sponges on top of instruments.

From the project folder:

    pip install ultralytics
    python nano/nano_train.py

The photos are in data/composites_real/train (jpg + json). This script
builds data/yolo/combined_new/train/images and train/labels, then trains.
Pass --previous for data/composites_previous.
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import yolo_layout


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--previous", action="store_true")
    parser.add_argument("--model", default="yolov8s.pt")
    parser.add_argument("--epochs", type=int, default=40)
    parser.add_argument("--imgsz", type=int, default=640)
    parser.add_argument("--batch", type=int, default=16)
    args = parser.parse_args()
    data = yolo_layout.combined_yaml(previous=args.previous)
    from ultralytics import YOLO

    YOLO(args.model).train(
        data=str(data.resolve()),
        epochs=args.epochs,
        imgsz=args.imgsz,
        batch=args.batch,
        project="runs",
        name="combined-previous" if args.previous else "combined-new",
        exist_ok=True,
    )


if __name__ == "__main__":
    main()
