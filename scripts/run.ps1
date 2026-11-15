# Builds and runs the whole app from a clean clone, on a single port (8000).
$ErrorActionPreference = "Stop"
Set-Location "$PSScriptRoot\.."

# Backend: one venv at the repo root (shared with scripts/dev.ps1 and the test suite).
if (-not (Test-Path ".venv")) {
    python -m venv .venv
}
. ".\.venv\Scripts\Activate.ps1"
pip install -r backend\requirements.txt -q

# Frontend: build once; FastAPI serves frontend/dist directly (see app/main.py).
Set-Location frontend
npm install --silent
npm run build

# Start
Set-Location ..\backend
uvicorn app.main:app --host 0.0.0.0 --port 8000
