"""Train the two small models that run on this GPU.

Counter: sponge count, trained on labeled generated trays.
Instrument: tool mask, trained on the full Kvasir-Instrument download.
"""
import json
import os
import random
import zipfile

import torch
import torch.nn as nn
from PIL import Image
from torch.utils.data import DataLoader, Dataset
from torchvision import transforms

import config
import photos

COUNT_PATH = os.path.join(config.MODEL_DIR, "count.pt")
TOOL_PATH = os.path.join(config.MODEL_DIR, "tool.pt")
REPORT_PATH = os.path.join(config.MODEL_DIR, "report.json")


def _device():
    return torch.device("cuda" if torch.cuda.is_available() else "cpu")


class CountNet(nn.Module):
    """Learns the sponge color thresholds, then turns that area into a count."""

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


def _to_tensor(image, size):
    image = image.convert("RGB").resize((size, size))
    return transforms.ToTensor()(image)


def train_counter(epochs=80):
    device = _device()
    train_x, train_y, test_x, test_y = [], [], [], []
    for count in range(16):
        for variant in range(2, 10):
            image, _tools = photos._draw(count, variant)
            train_x.append(_to_tensor(image, 160))
            train_y.append(float(count))
        for variant in range(2):
            image, _tools = photos._draw(count, variant)
            test_x.append(_to_tensor(image, 160))
            test_y.append(float(count))
    train_x = torch.stack(train_x).to(device)
    train_y = torch.tensor(train_y, device=device)
    test_x = torch.stack(test_x).to(device)
    model = CountNet().to(device)
    opt = torch.optim.Adam(model.parameters(), lr=0.02)
    loss_fn = nn.SmoothL1Loss()
    for epoch in range(epochs):
        model.train()
        opt.zero_grad()
        loss = loss_fn(model(train_x), train_y)
        loss.backward()
        opt.step()
        if epoch % 20 == 19:
            print(f"count epoch {epoch + 1} loss {float(loss.detach()):.4f}", flush=True)
    model.eval()
    with torch.no_grad():
        raw = model(test_x).clamp(0, 20).cpu()
    exact = 0
    abs_err = 0.0
    for pred, truth in zip(raw.tolist(), test_y):
        guess = int(round(pred))
        exact += int(guess == int(truth))
        abs_err += abs(guess - int(truth))
    n = len(test_y)
    torch.save({"state": model.state_dict(), "exact": exact, "n": n, "mae": round(abs_err / n, 3)}, COUNT_PATH)
    print(f"count held-out {exact}/{n} exact mae {abs_err / n:.3f}", flush=True)
    return {"exact": exact, "n": n, "mae": round(abs_err / n, 3)}


def _kvasir_root():
    import tarfile
    root = os.path.join(config.EXTERNAL_DIR, "kvasir-instrument")
    zip_path = os.path.join(config.EXTERNAL_DIR, "kvasir-instrument.zip")
    if not os.path.isdir(root):
        if not os.path.isfile(zip_path):
            raise SystemExit("Kvasir zip is not downloaded yet")
        os.makedirs(root, exist_ok=True)
        with zipfile.ZipFile(zip_path) as handle:
            handle.extractall(config.EXTERNAL_DIR)
    for dirpath, _dirs, files in os.walk(root):
        for name in files:
            if name.endswith(".tar.gz"):
                with tarfile.open(os.path.join(dirpath, name)) as handle:
                    handle.extractall(dirpath)
                os.remove(os.path.join(dirpath, name))
    return root


def _kvasir_pairs(root):
    images = []
    masks = []
    for dirpath, _dirs, files in os.walk(root):
        low = dirpath.lower()
        for name in files:
            path = os.path.join(dirpath, name)
            if name.lower().endswith((".jpg", ".jpeg")) and "mask" not in low:
                images.append(path)
            elif name.lower().endswith(".png") and "mask" in low:
                masks.append(path)
    by_stem = {os.path.splitext(os.path.basename(path))[0]: path for path in masks}
    pairs = []
    for path in images:
        stem = os.path.splitext(os.path.basename(path))[0]
        if stem in by_stem:
            pairs.append((path, by_stem[stem]))
    if not pairs:
        raise SystemExit(f"No image/mask pairs under {root}")
    return pairs


def train_tools(epochs=8):
    device = _device()
    pairs = _kvasir_pairs(_kvasir_root())
    random.Random(3).shuffle(pairs)
    split = max(1, int(len(pairs) * 0.85))
    train_pairs, test_pairs = pairs[:split], pairs[split:]
    model = ToolNet().to(device)
    opt = torch.optim.Adam(model.parameters(), lr=1e-3)
    loss_fn = nn.BCEWithLogitsLoss()
    for epoch in range(epochs):
        model.train()
        total = 0.0
        for image_path, mask_path in train_pairs:
            image = _to_tensor(Image.open(image_path), 128).unsqueeze(0).to(device)
            mask = Image.open(mask_path).convert("L").resize((128, 128))
            target = transforms.ToTensor()(mask).unsqueeze(0).to(device)
            target = (target > 0.5).float()
            opt.zero_grad()
            pred = model(image)
            loss = loss_fn(pred, target)
            loss.backward()
            opt.step()
            total += float(loss)
        print(f"tool epoch {epoch + 1} loss {total / len(train_pairs):.4f}", flush=True)
    model.eval()
    inter = 0.0
    union = 0.0
    with torch.no_grad():
        for image_path, mask_path in test_pairs:
            image = _to_tensor(Image.open(image_path), 128).unsqueeze(0).to(device)
            mask = Image.open(mask_path).convert("L").resize((128, 128))
            target = transforms.ToTensor()(mask)
            target = (target > 0.5).float()
            pred = torch.sigmoid(model(image)[0].cpu()) > 0.5
            inter += float((pred & target.bool()).sum())
            union += float((pred | target.bool()).sum())
    iou = inter / max(union, 1.0)
    sample_dir = os.path.join(config.EXTERNAL_DIR, "kvasir-samples")
    os.makedirs(sample_dir, exist_ok=True)
    names = []
    for image_path, _mask in test_pairs[:8]:
        name = os.path.basename(image_path)
        Image.open(image_path).convert("RGB").save(os.path.join(sample_dir, name), quality=90)
        names.append(name)
    torch.save({"state": model.state_dict(), "iou": round(iou, 3), "n_train": len(train_pairs), "n_test": len(test_pairs), "samples": names}, TOOL_PATH)
    print(f"tool held-out IoU {iou:.3f} on {len(test_pairs)}", flush=True)
    return {"iou": round(iou, 3), "n_train": len(train_pairs), "n_test": len(test_pairs), "samples": names}


def main():
    report = {
        "device": str(_device()),
        "counter": train_counter(),
        "tool": train_tools(),
        "gated": [
            "MM-OR needs the author form before the 500 GB download",
            "4D-OR needs the author form",
            "MVOR is released by request",
            "Cholec80, CholecT50, and EndoVis need a request form",
        ],
    }
    with open(REPORT_PATH, "w", encoding="utf-8") as handle:
        json.dump(report, handle, indent=2)
    print(json.dumps(report, indent=2), flush=True)


if __name__ == "__main__":
    main()
