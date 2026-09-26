"""Train CountNet and ToolNet. This is the script for the others folder.

From the project folder:

    python others/train.py

CountNet learns sponge color on generated trays from app/photos.py.
It does not use IGauze or HOSPI. Held-out check is 32 drawn photos.

ToolNet learns an instrument mask on Kvasir-Instrument:
    data/external/kvasir-instrument
501 train images, 89 test images. Those photos are endoscope tools,
not overhead trays.

Weights are written to models/count.pt and models/tool.pt.
Copy them to others/weights/ after training if you are packing the Nano.
"""
import sys
from pathlib import Path

APP = Path(__file__).resolve().parents[1] / "app"
sys.path.insert(0, str(APP))

import train_local


if __name__ == "__main__":
    train_local.main()
