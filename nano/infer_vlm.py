"""One tray photo through the vision model on port 8001.

The weight is Qwen/Qwen2.5-VL-7B-Instruct, or the fine-tune after
bash train_on_nano.sh. Start it first:

    bash serve_zrt.sh

Then:

    python infer_vlm.py path/to/tray.jpg

That file is pulled by ZRT on the Nano. It is not stored in this folder.
Training set for the fine-tune is HOSPI instrument photos.
"""
import base64
import json
import sys
import urllib.request
from pathlib import Path

URL = "http://100.81.221.41:8001/v1/chat/completions"
MODEL = "Qwen/Qwen2.5-VL-7B-Instruct"


def main():
    if len(sys.argv) < 2:
        raise SystemExit("usage: python infer_vlm.py path/to/tray.jpg")
    image = Path(sys.argv[1])
    mime = "image/png" if image.suffix.lower() == ".png" else "image/jpeg"
    encoded = base64.b64encode(image.read_bytes()).decode()
    body = json.dumps({
        "model": MODEL,
        "temperature": 0,
        "max_tokens": 16,
        "messages": [{"role": "user", "content": [
            {"type": "image_url", "image_url": {"url": f"data:{mime};base64,{encoded}"}},
            {"type": "text", "text": "How many gauze sponges are on the tray? Answer with a number only."},
        ]}],
    }).encode()
    request = urllib.request.Request(URL, data=body, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(request, timeout=60) as response:
        data = json.loads(response.read().decode())
    print(data["choices"][0]["message"]["content"])


if __name__ == "__main__":
    main()
