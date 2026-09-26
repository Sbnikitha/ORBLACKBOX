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

# Three inference boxes. Same ports. The command center switches which host is live.
NANO2_HOST = os.getenv("NANO2_HOST", "100.82.233.80")
HOSTS = (
    {"id": "local", "label": "Local", "host": "127.0.0.1"},
    {"id": "nano1", "label": "Nano 1", "host": "100.81.221.41"},
    {"id": "nano2", "label": "Nano 2", "host": NANO2_HOST},
)
INFER_PORTS = {
    "Detector": 8002,
    "CountNet": 8003,
    "ToolNet": 8004,
    "Whisper": 8005,
    "Language": 8006,
    "TrayCount": 8007,
    "Qwen3 27B": 8000,
    "Qwen2.5-VL": 8001,
}
ACTIVE_HOST = "nano1"
INFER_HOST = HOSTS[1]["host"]
LLM_URL = os.getenv("LLM_URL", f"http://{INFER_HOST}:{INFER_PORTS['Qwen3 27B']}/v1")
VLM_URL = os.getenv("VLM_URL", f"http://{INFER_HOST}:{INFER_PORTS['Qwen2.5-VL']}/v1")


def apply_host(host_id):
    """Point every model port at one of the three boxes."""
    global ACTIVE_HOST, INFER_HOST, LLM_URL, VLM_URL
    found = next((item for item in HOSTS if item["id"] == host_id), None)
    if found is None:
        raise ValueError("Unknown box")
    if not found["host"]:
        raise ValueError("Nano 2 address is not set")
    ACTIVE_HOST = found["id"]
    INFER_HOST = found["host"]
    LLM_URL = f"http://{INFER_HOST}:{INFER_PORTS['Qwen3 27B']}/v1"
    VLM_URL = f"http://{INFER_HOST}:{INFER_PORTS['Qwen2.5-VL']}/v1"
    return found
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
