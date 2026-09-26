#!/bin/bash
# Free the Nano GPU before training.
tmux kill-session -t llm 2>/dev/null && echo "Stopped 27B model"
tmux kill-session -t vlm 2>/dev/null && echo "Stopped vision model"
echo "GPU released for training"
