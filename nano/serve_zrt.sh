#!/bin/bash
# Serve the two ZRT models. Vision uses the fine-tune after it exists.
# Before that, set VLM=Qwen/Qwen2.5-VL-7B-Instruct
set -u
NANO="$(cd "$(dirname "$0")" && pwd)"
LOG_DIR="$NANO/logs"
mkdir -p "$LOG_DIR"
LLM="${LLM:-Inferact/Qwen3.8-27B-NVFP4}"
VLM="${VLM:-Qwen/Qwen2.5-VL-7B-Instruct}"
echo "[$(date '+%Y-%m-%d %H:%M:%S')] serve LLM $LLM  VLM $VLM" | tee -a "$LOG_DIR/serve.log"

if ! tmux has-session -t llm 2>/dev/null; then
  tmux new -d -s llm "zrt serve $LLM --host 0.0.0.0 --port 8000 --gpu-memory-utilization 0.50 --max-model-len 8192 2>&1 | tee -a $LOG_DIR/llm.log"
  echo "Started 27B on port 8000. Log: $LOG_DIR/llm.log"
else
  echo "27B already running"
fi
if ! tmux has-session -t vlm 2>/dev/null; then
  tmux new -d -s vlm "zrt serve $VLM --host 0.0.0.0 --port 8001 --gpu-memory-utilization 0.25 --max-model-len 4096 2>&1 | tee -a $LOG_DIR/vlm.log"
  echo "Started vision on port 8001. Log: $LOG_DIR/vlm.log"
else
  echo "Vision model already running"
fi
echo "Loading takes a few minutes. Check with: curl localhost:8000/v1/models"
