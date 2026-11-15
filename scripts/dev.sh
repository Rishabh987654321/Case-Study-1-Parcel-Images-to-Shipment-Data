#!/bin/bash
# Development mode: backend on :8000 with --reload, Vite dev server on :5173
# (proxying /api to :8000, see frontend/vite.config.ts). Ctrl-C stops both.
set -e
cd "$(dirname "$0")/.."

source .venv/bin/activate

(cd backend && uvicorn app.main:app --reload --port 8000) &
BACKEND_PID=$!
trap "kill $BACKEND_PID 2>/dev/null" EXIT

cd frontend
npm run dev
