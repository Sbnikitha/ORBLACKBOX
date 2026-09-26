"""One sentence through the language model on port 8000.

The weight is Inferact/Qwen3.8-27B-NVFP4. Start it first:

    bash serve_zrt.sh

Then:

    python infer_llm.py "Adding five sponges."

That file is pulled by ZRT on the Nano. It is not stored in this folder.
"""
import json
import sys
import urllib.request

URL = "http://127.0.0.1:8000/v1/chat/completions"
MODEL = "Inferact/Qwen3.8-27B-NVFP4"


def main():
    if len(sys.argv) < 2:
        raise SystemExit('usage: python infer_llm.py "Adding five sponges."')
    text = " ".join(sys.argv[1:])
    body = json.dumps({
        "model": MODEL,
        "temperature": 0,
        "max_tokens": 80,
        "messages": [
            {"role": "system", "content": 'Reply ONLY with JSON {"added": int, "removed": int}.'},
            {"role": "user", "content": text},
        ],
    }).encode()
    request = urllib.request.Request(URL, data=body, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(request, timeout=60) as response:
        data = json.loads(response.read().decode())
    print(data["choices"][0]["message"]["content"])


if __name__ == "__main__":
    main()
