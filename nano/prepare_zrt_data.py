"""Turn HOSPI photos into the JSONL the Nano vision fine-tune reads.

Each line is image, question, answer. Test photos stay in test.jsonl.
"""
import argparse
import json
import os
import re
from pathlib import Path


QUESTION = "What surgical instrument is in this photo? Reply with the instrument name only."


def instrument_name(path):
    stem = Path(path).stem
    stem = re.sub(r"_Add\d+$", "", stem, flags=re.I)
    stem = re.sub(r"_\d+$", "", stem)
    stem = re.sub(r"^\d+_", "", stem)
    return stem.replace("_", " ").strip() or "unknown instrument"


def object_count(image_path):
    label = str(image_path).replace(f"{os.sep}images{os.sep}", f"{os.sep}labels{os.sep}")
    label = str(Path(label).with_suffix(".txt"))
    if not os.path.isfile(label):
        return None
    with open(label, encoding="utf-8") as handle:
        return sum(1 for line in handle if line.strip())


def split_for(path):
    parts = {part.lower() for part in Path(path).parts}
    if "test" in parts or "val" in parts:
        return "test"
    return "train"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--hospi", required=True, help="Folder that contains the HOSPI images")
    parser.add_argument("--out", default="data", help="Where train.jsonl and test.jsonl are written")
    parser.add_argument("--max-images", type=int, default=0, help="0 means every image")
    args = parser.parse_args()
    root = Path(args.hospi).expanduser()
    if not root.is_dir():
        raise SystemExit(f"HOSPI folder not found: {root}")
    out = Path(args.out).expanduser()
    out.mkdir(parents=True, exist_ok=True)
    rows = {"train": [], "test": []}
    seen = 0
    for dirpath, _dirs, files in os.walk(root):
        for name in sorted(files):
            if not name.lower().endswith((".jpg", ".jpeg", ".png")):
                continue
            path = os.path.join(dirpath, name)
            name_text = instrument_name(path)
            count = object_count(path)
            answer = name_text if count is None else f"{name_text}. Count {count}."
            rows[split_for(path)].append({
                "image": os.path.abspath(path),
                "question": QUESTION,
                "answer": answer,
            })
            seen += 1
    if args.max_images:
        rows["train"] = rows["train"][: args.max_images]
        rows["test"] = rows["test"][: max(1, args.max_images // 4)]
    for split, items in rows.items():
        dest = out / f"{split}.jsonl"
        with open(dest, "w", encoding="utf-8") as handle:
            for item in items:
                handle.write(json.dumps(item) + "\n")
        print(f"wrote {dest} lines {len(items)}", flush=True)
    if not rows["train"]:
        raise SystemExit("No training images found under " + str(root))
    print(f"total images {sum(len(v) for v in rows.values())}", flush=True)


if __name__ == "__main__":
    main()
