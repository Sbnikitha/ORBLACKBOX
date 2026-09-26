#!/bin/sh
# OR Sentinel on a Nano or any Linux box. The command center does not need a GPU.
set -e
cd "$(dirname "$0")"
python3 -m venv .venv
. .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
python -m unittest tests.test_sentinel -v
echo ""
echo "Command center: http://127.0.0.1:8501"
echo "Interactive pitch: http://127.0.0.1:8501/pitch"
exec python -m uvicorn app.server:app --host 0.0.0.0 --port 8501
