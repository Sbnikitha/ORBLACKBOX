"""Load the GPU-trained counter and instrument mask and run one image."""
import json
import os

import config

_COUNT = None
_TOOL = None
_DEVICE = None


def report():
    path = os.path.join(config.MODEL_DIR, "report.json")
    if os.path.isfile(path):
        with open(path, encoding="utf-8") as handle:
            data = json.load(handle)
        data["ready"] = True
        return data
    count_path = os.path.join(config.MODEL_DIR, "count.pt")
    if not os.path.isfile(count_path):
        return {"ready": False}
    import torch
    blob = torch.load(count_path, map_location="cpu", weights_only=False)
    return {"ready": True, "device": "saved", "counter": {"exact": blob.get("exact"), "n": blob.get("n"), "mae": blob.get("mae")}, "tool": {}}


def _device():
    global _DEVICE
    if _DEVICE is None:
        import torch
        _DEVICE = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    return _DEVICE


def _count_model():
    global _COUNT
    if _COUNT is None:
        import torch
        import train_local
        _COUNT = train_local.CountNet()
        blob = torch.load(os.path.join(config.MODEL_DIR, "count.pt"), map_location=_device(), weights_only=False)
        _COUNT.load_state_dict(blob["state"])
        _COUNT.to(_device()).eval()
    return _COUNT


def count_image(image):
    import torch
    from torchvision import transforms
    model = _count_model()
    batch = transforms.ToTensor()(image.convert("RGB").resize((160, 160))).unsqueeze(0).to(_device())
    with torch.no_grad():
        value = float(model(batch)[0].clamp(0, 20))
    return int(round(value)), round(value, 2)


def _tool_model():
    global _TOOL
    if _TOOL is None:
        import torch
        import train_local
        _TOOL = train_local.ToolNet()
        blob = torch.load(os.path.join(config.MODEL_DIR, "tool.pt"), map_location=_device(), weights_only=False)
        _TOOL.load_state_dict(blob["state"])
        _TOOL.to(_device()).eval()
        _TOOL.samples = blob.get("samples") or []
    return _TOOL


def tool_box(image):
    import torch
    from torchvision import transforms
    model = _tool_model()
    size = 128
    batch = transforms.ToTensor()(image.convert("RGB").resize((size, size))).unsqueeze(0).to(_device())
    with torch.no_grad():
        mask = torch.sigmoid(model(batch)[0, 0]).cpu()
    ys, xs = torch.where(mask > 0.7)
    if len(xs) == 0:
        return None
    scale_x = image.width / size
    scale_y = image.height / size
    return {
        "x": int(xs.min() * scale_x),
        "y": int(ys.min() * scale_y),
        "w": int((xs.max() - xs.min() + 1) * scale_x),
        "h": int((ys.max() - ys.min() + 1) * scale_y),
        "kind": "instrument",
        "label": "trained tool",
    }
