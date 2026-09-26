"""Render deliverables/metrics.gif from the logged benchmark scores."""
import os

from PIL import Image, ImageDraw, ImageFont

ROOT = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(ROOT, "metrics.gif")
W, H = 1280, 720
BG = (7, 17, 14)
CARD = (12, 32, 27)
INK = (232, 247, 241)
MUTED = (142, 170, 160)
SAFE = (62, 224, 162)
GOLD = (255, 193, 77)
TRACK = (28, 48, 42)

ROWS = [
    ("COMBINED YOLO  mAP50", 88.4, "88.4%", SAFE, "Epoch 39 of 40. Found the object."),
    ("DETECTOR RECALL", 81.7, "81.7%", SAFE, "A missed sponge is the failure that matters."),
    ("COUNTNET EXACT", 78.1, "78.1%", GOLD, "25 of 32 trays. Off by one blocks the close."),
    ("TOOLNET MASK IoU", 56.7, "56.7%", GOLD, "89 test frames. A box, not a lock."),
    ("FUSION RULES", 100, "16/16", SAFE, "The model does not choose BLOCK."),
]


def font(size, bold=False):
    name = "segoeuib.ttf" if bold else "segoeui.ttf"
    return ImageFont.truetype(os.path.join(os.environ["WINDIR"], "Fonts", name), size)


def ease(t):
    t = max(0, min(1, t))
    return 1 - (1 - t) ** 3


def frame(step, total_grow=28):
    image = Image.new("RGB", (W, H), BG)
    draw = ImageDraw.Draw(image)
    draw.rectangle((0, 0, 10, H), fill=SAFE)
    title = font(54, True)
    small = font(22)
    mono = font(18)
    draw.text((48, 36), "OR SENTINEL", font=mono, fill=SAFE)
    draw.text((48, 68), "Benchmarks", font=title, fill=INK)
    draw.text((360, 92), "See the tray. Then hold the close.", font=small, fill=MUTED)
    t = ease(step / total_grow)
    top = 170
    for i, (label, pct, shown, color, why) in enumerate(ROWS):
        y = top + i * 96
        draw.rounded_rectangle((48, y, 1232, y + 84), radius=16, fill=CARD)
        draw.text((72, y + 12), label, font=mono, fill=MUTED)
        draw.text((72, y + 40), why, font=small, fill=INK)
        value = shown if t >= 1 else (f"{pct * t:.1f}%" if shown.endswith("%") else shown)
        if shown == "16/16" and t < 1:
            value = f"{int(round(16 * t))}/16"
        draw.text((1040, y + 22), value, font=font(32, True), fill=color)
        x0, x1, yb = 620, 1000, y + 58
        draw.rounded_rectangle((x0, yb, x1, yb + 10), radius=5, fill=TRACK)
        fill_to = x0 + int((x1 - x0) * (pct / 100) * t)
        if fill_to > x0 + 4:
            draw.rounded_rectangle((x0, yb, fill_to, yb + 10), radius=5, fill=color)
    draw.text((48, 672), "Qwen2.5-VL: training script only. No evaluation score yet.  Not a medical device.", font=mono, fill=MUTED)
    return image


def main():
    grow, hold = 28, 14
    frames = [frame(i, grow) for i in range(grow + 1)]
    frames += [frames[-1]] * hold
    frames[0].save(OUT, save_all=True, append_images=frames[1:], duration=70, loop=0, optimize=True)
    print(OUT, os.path.getsize(OUT))


if __name__ == "__main__":
    main()
