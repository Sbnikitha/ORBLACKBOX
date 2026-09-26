"""Run the two small models that are not the tray detector.

Paste this others folder onto the Nano, then:

    pip install torch torchvision pillow
    python infer.py path/to/image.jpg

Weights:
    weights/count.pt   CountNet, sponge count
    weights/tool.pt    ToolNet, instrument outline

Training script: train.py
CountNet dataset: generated sponge trays drawn by the app (32 held-out photos).
ToolNet dataset: Kvasir-Instrument, data/external/kvasir-instrument
    (501 train images, 89 test images).
"""
import sys
from pathlib import Path

import torch
import torch.nn as nn
from PIL import Image
from torchvision import transforms

DIR = Path(__file__).resolve().parent
COUNT_PATH = DIR / "weights" / "count.pt"
TOOL_PATH = DIR / "weights" / "tool.pt"


class CountNet(nn.Module):
    def __init__(self):
        super().__init__()
        self.rt = nn.Parameter(torch.tensor(0.72))
        self.gt = nn.Parameter(torch.tensor(0.58))
        self.bt = nn.Parameter(torch.tensor(0.50))
        self.scale = nn.Parameter(torch.tensor(80.0))
        self.bias = nn.Parameter(torch.tensor(-1.0))

    def forward(self, batch):
        red, green, blue = batch[:, 0:1], batch[:, 1:2], batch[:, 2:3]
        heat = (
            torch.sigmoid((red - self.rt) * 40)
            * torch.sigmoid((green - self.gt) * 40)
            * torch.sigmoid((blue - self.bt) * 40)
        )
        return heat.mean(dim=(1, 2, 3)) * self.scale + self.bias


class ToolNet(nn.Module):
    def __init__(self):
        super().__init__()
        self.net = nn.Sequential(
            nn.Conv2d(3, 16, 3, padding=1), nn.ReLU(), nn.MaxPool2d(2),
            nn.Conv2d(16, 32, 3, padding=1), nn.ReLU(), nn.MaxPool2d(2),
            nn.Conv2d(32, 64, 3, padding=1), nn.ReLU(), nn.MaxPool2d(2),
            nn.ConvTranspose2d(64, 32, 2, stride=2), nn.ReLU(),
            nn.ConvTranspose2d(32, 16, 2, stride=2), nn.ReLU(),
            nn.ConvTranspose2d(16, 1, 2, stride=2),
        )

    def forward(self, batch):
        return self.net(batch)


def main():
    if len(sys.argv) < 2:
        raise SystemExit("usage: python infer.py path/to/image.jpg")
    image = Image.open(sys.argv[1]).convert("RGB")
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    counter = CountNet()
    counter.load_state_dict(torch.load(COUNT_PATH, map_location=device, weights_only=False)["state"])
    counter.to(device).eval()
    batch = transforms.ToTensor()(image.resize((160, 160))).unsqueeze(0).to(device)
    with torch.no_grad():
        raw = float(counter(batch)[0].clamp(0, 20))
    print(f"count {int(round(raw))} raw {raw:.2f}")

    tool = ToolNet()
    tool.load_state_dict(torch.load(TOOL_PATH, map_location=device, weights_only=False)["state"])
    tool.to(device).eval()
    size = 128
    batch = transforms.ToTensor()(image.resize((size, size))).unsqueeze(0).to(device)
    with torch.no_grad():
        mask = torch.sigmoid(tool(batch)[0, 0]).cpu()
    ys, xs = torch.where(mask > 0.7)
    if len(xs) == 0:
        print("tool none")
        return
    print(
        f"tool box x {int(xs.min() * image.width / size)} "
        f"y {int(ys.min() * image.height / size)} "
        f"w {int((xs.max() - xs.min() + 1) * image.width / size)} "
        f"h {int((ys.max() - ys.min() + 1) * image.height / size)}"
    )


if __name__ == "__main__":
    main()
