"""Every setting in one place. Change values here, not in other files."""
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(ROOT, "data")
PHOTO_DIR = os.path.join(DATA_DIR, "photos")
AUDIO_DIR = os.path.join(DATA_DIR, "audio")
STATE_DIR = os.path.join(ROOT, "state")
BENCH_DIR = os.path.join(ROOT, "bench")
MODEL_DIR = os.path.join(ROOT, "models")
EXTERNAL_DIR = os.path.join(DATA_DIR, "external")

OFFLINE_FLAG = os.path.join(STATE_DIR, "OFFLINE")
VISION_DOWN = os.path.join(STATE_DIR, "VISION_DOWN")

# "local" runs the on-box models in this repo.
# Point these at ZRT (http://localhost:8000/v1 and :8001/v1) on a Nano.
LLM_URL = os.getenv("LLM_URL", "local")
VLM_URL = os.getenv("VLM_URL", "local")
LLM_MODEL = os.getenv("LLM_MODEL", "or-sentinel-edge")
VLM_MODEL = os.getenv("VLM_MODEL", "or-sentinel-traycount")

CLOUD_URL = os.getenv("CLOUD_URL", "simulated")
CLOUD_KEY = os.getenv("CLOUD_KEY", "")
CLOUD_MODEL = os.getenv("CLOUD_MODEL", "protocol-desk")

CONFIDENCE_THRESHOLD = float(os.getenv("CONFIDENCE_THRESHOLD", "0.7"))
LONG_SURGERY_MIN = 360
REQUEST_TIMEOUT_S = 8
ALLOW_FALLBACK = os.getenv("ALLOW_FALLBACK", "1") != "0"

os.makedirs(STATE_DIR, exist_ok=True)
os.makedirs(AUDIO_DIR, exist_ok=True)
os.makedirs(PHOTO_DIR, exist_ok=True)
os.makedirs(MODEL_DIR, exist_ok=True)
os.makedirs(EXTERNAL_DIR, exist_ok=True)
