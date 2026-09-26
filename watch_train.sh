#!/bin/bash
# Follow the newest training log. Ctrl+C stops watching. Training keeps going.
NANO="$(cd "$(dirname "$0")" && pwd)"
LOG="$(ls -1t "$NANO"/logs/train_*.log 2>/dev/null | head -n 1)"
if [ -z "$LOG" ]; then
  echo "No train log yet. Start with: HOSPI_DIR=~/hospi bash nano/train_on_nano.sh"
  exit 1
fi
echo "Watching $LOG"
tail -f "$LOG"
