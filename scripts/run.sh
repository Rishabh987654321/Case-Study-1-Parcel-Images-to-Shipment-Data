#!/bin/bash
# Builds and runs the whole app from a clean clone, on a single port (8000).
set -e
cd "$(dirname "$0")/.."

# Backend: one venv at the repo root (shared with scripts/dev.sh and the test suite).
python3 -m venv .venv 2>/dev/null || true
source .venv/bin/activate
pip install -r backend/requirements.txt -q

# Frontend: build once; FastAPI serves frontend/dist directly (see app/main.py).
cd frontend
npm install --silent
npm run build

# Start
cd ../backend
uvicorn app.main:app --host 0.0.0.0 --port 8000
