# OR Sentinel on Windows. The command center does not need a GPU.
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m unittest tests.test_sentinel -v
Write-Host ""
Write-Host "Command center: http://127.0.0.1:8501"
Write-Host "Interactive pitch: http://127.0.0.1:8501/pitch"
.\.venv\Scripts\python.exe -m uvicorn app.server:app --host 127.0.0.1 --port 8501
