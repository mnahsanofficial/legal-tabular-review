#!/usr/bin/env bash
# Start backend (FastAPI) and frontend (Next.js) from repo root.
# Run: ./scripts/start-all.sh   or   bash scripts/start-all.sh

set -e
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

# Backend: ensure venv and deps
if [ ! -d backend/.venv ]; then
  echo "Creating backend venv..."
  python3 -m venv backend/.venv
fi
backend/.venv/bin/pip install -q -r backend/requirements.txt 2>/dev/null || true

# Start backend in background
echo "Starting backend on http://127.0.0.1:4000 ..."
backend/.venv/bin/uvicorn app:app --host 127.0.0.1 --port 4000 --app-dir backend &
BACKEND_PID=$!

# Frontend: ensure deps
if [ ! -d frontend/node_modules ]; then
  echo "Installing frontend deps..."
  (cd frontend && npm install)
fi

# Start frontend
echo "Starting frontend on http://localhost:3000 ..."
(cd frontend && npm run dev) &
FRONTEND_PID=$!

echo ""
echo "Backend PID: $BACKEND_PID  |  Frontend PID: $FRONTEND_PID"
echo "Backend:  http://127.0.0.1:4000  (health: GET /health)"
echo "Frontend: http://localhost:3000"
echo "Stop with: kill $BACKEND_PID $FRONTEND_PID"
wait
