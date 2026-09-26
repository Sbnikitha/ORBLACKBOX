#!/bin/bash
# Fine-tune the vision model on the Nano, then it is served by ZRT.
# Paste this folder onto the Nano and run:
#   HOSPI_DIR=~/hospi bash nano/train_on_nano.sh
# Every line is saved under nano/logs/train_*.log
set -u

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
NANO="$(cd "$(dirname "$0")" && pwd)"
HOSPI_DIR="${HOSPI_DIR:-$HOME/hospi}"
HP_REPO="${HP_REPO:-$HOME/Desktop/Med_VLM_Fine-Tune_vLLM}"
LOG_DIR="$NANO/logs"
STAMP="$(date +%Y%m%d_%H%M%S)"
LOG="$LOG_DIR/train_${STAMP}.log"
mkdir -p "$LOG_DIR" "$ROOT/data/zrt"

log() { echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*"; }

exec > >(tee -a "$LOG") 2>&1

log "OR Sentinel vision fine-tune start"
log "log file $LOG"
log "host $(hostname)"
log "HOSPI_DIR $HOSPI_DIR"
log "HP_REPO $HP_REPO"
log "pwd $(pwd)"
nvidia-smi || log "nvidia-smi not available"
free -h || true
df -h "$ROOT" || true
command -v zrt && zrt models || log "zrt is not on PATH yet"

log "building train.jsonl and test.jsonl"
python3 "$NANO/prepare_zrt_data.py" --hospi "$HOSPI_DIR" --out "$ROOT/data/zrt"
log "train lines $(wc -l < "$ROOT/data/zrt/train.jsonl")"
log "test lines $(wc -l < "$ROOT/data/zrt/test.jsonl")"
log "first train row:"
head -n 1 "$ROOT/data/zrt/train.jsonl"

log "stopping served ZRT models so the GPU is free for training"
bash "$NANO/stop_zrt.sh" || true

if [ ! -d "$HP_REPO" ]; then
  log "cloning HP Med_VLM_Fine-Tune_vLLM"
  git clone https://github.com/jrgosalvez/Med_VLM_Fine-Tune_vLLM.git "$HP_REPO"
fi
cd "$HP_REPO"
chmod +x ./*.sh 2>/dev/null || true
log "HP repo files:"
ls -la

if [ ! -f finetune_qwen2_5_vl.sh ]; then
  log "finetune_qwen2_5_vl.sh is missing. Read README.md in $HP_REPO and point it at $ROOT/data/zrt/train.jsonl"
  exit 1
fi

cp -n finetune_qwen2_5_vl.sh finetune_qwen2_5_vl.sh.original || true
log "data fields the HP script mentions:"
grep -n -i -E "dataset|load_dataset|jsonl|question|answer|image" ./*.sh ./*.py 2>/dev/null | head -n 80 || true

export TRAIN_JSONL="$ROOT/data/zrt/train.jsonl"
export TEST_JSONL="$ROOT/data/zrt/test.jsonl"
export QFORMAT="${QFORMAT:-nvfp4}"
export STAGE="${STAGE:-all}"
log "STAGE $STAGE QFORMAT $QFORMAT"
log "training command: STAGE=$STAGE QFORMAT=$QFORMAT bash finetune_qwen2_5_vl.sh"
log "If the script reads a Hugging Face dataset name instead of TRAIN_JSONL, change that name to the jsonl path above and run this script again."

STAGE="$STAGE" QFORMAT="$QFORMAT" bash finetune_qwen2_5_vl.sh
STATUS=$?
log "HP fine-tune exit $STATUS"
log "when the model is on Hugging Face, serve it with: VLM=<you>/or-sentinel-vision bash $NANO/serve_zrt.sh"
exit "$STATUS"
