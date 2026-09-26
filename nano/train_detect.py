"""Train one object detector for sponges and instruments.

Unzip the dataset bundle and run this file from that folder:

    pip install ultralytics
    python train_detect.py

The default set is combined_new: real IGauze trays with HOSPI tools under the sponges.
Labels are gauze, red gauze, stained gauze, hand, stained hand, and instrument.

Other sets in the same zip:

    python train_detect.py --data combined_previous/data.yaml
    python train_detect.py --data igauze/data.yaml
    python train_detect.py --data hospi_yolo/data.yaml
"""
import argparse
from pathlib import Path


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--data", default="combined_new/data.yaml")
    parser.add_argument("--model", default="yolov8s.pt")
    parser.add_argument("--epochs", type=int, default=40)
    parser.add_argument("--imgsz", type=int, default=640)
    parser.add_argument("--batch", type=int, default=16)
    parser.add_argument("--name", default="or-sentinel-detect")
    args = parser.parse_args()
    data = Path(args.data)
    if not data.is_file():
        raise SystemExit(f"Missing {data}. Unzip the bundle and run this script from that folder.")
    from ultralytics import YOLO

    model = YOLO(args.model)
    model.train(
        data=str(data.resolve()),
        epochs=args.epochs,
        imgsz=args.imgsz,
        batch=args.batch,
        project="runs",
        name=args.name,
        exist_ok=True,
    )


if __name__ == "__main__":
    main()
