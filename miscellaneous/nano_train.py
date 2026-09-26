"""Train on the Nano now: sponges on top of instruments.

Unzip OR_Sentinel_datasets.zip and run this from that folder:

    pip install ultralytics
    python nano_train.py

That uses combined_new, the set where gauze covers the tools.
Pass --previous to train the earlier combined set instead.
"""
import argparse
from pathlib import Path


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--previous", action="store_true")
    parser.add_argument("--model", default="yolov8s.pt")
    parser.add_argument("--epochs", type=int, default=40)
    parser.add_argument("--imgsz", type=int, default=640)
    parser.add_argument("--batch", type=int, default=16)
    args = parser.parse_args()
    data = Path("combined_previous/data.yaml" if args.previous else "combined_new/data.yaml")
    if not data.is_file():
        raise SystemExit(f"Missing {data}. Unzip the bundle and run this script from that folder.")
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
