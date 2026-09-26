"""Turn a wav into text with Whisper tiny.

Paste the nano folder onto the Nano, then:

    pip install openai-whisper
    python infer_whisper.py path/to/line.wav

Weight: weights/whisper/tiny.pt
This is the speech model. It is not trained here. The file is OpenAI Whisper tiny.
The Counter and Checklist read the text this prints.
"""
import sys
import wave
from pathlib import Path

import numpy as np

WEIGHT_DIR = Path(__file__).resolve().parent / "weights" / "whisper"


def _audio(path):
    with wave.open(path) as handle:
        rate = handle.getframerate()
        channels = handle.getnchannels()
        frames = np.frombuffer(handle.readframes(handle.getnframes()), dtype=np.int16).astype(np.float32)
        frames /= 32768.0
    if channels > 1:
        frames = frames.reshape(-1, channels).mean(axis=1)
    if rate == 16000:
        return frames
    length = int(len(frames) * 16000 / rate)
    return np.interp(np.linspace(0, len(frames) - 1, length), np.arange(len(frames)), frames).astype(np.float32)


def main():
    if len(sys.argv) < 2:
        raise SystemExit("usage: python infer_whisper.py path/to/line.wav")
    weight = WEIGHT_DIR / "tiny.pt"
    if not weight.is_file():
        raise SystemExit(f"Missing {weight}")
    import whisper

    model = whisper.load_model("tiny", download_root=str(WEIGHT_DIR))
    text = model.transcribe(_audio(sys.argv[1]), fp16=False, language="en")["text"].strip()
    print(text)


if __name__ == "__main__":
    main()
