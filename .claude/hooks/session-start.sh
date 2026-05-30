#!/usr/bin/env bash
# SessionStart hook: ensure this ephemeral environment has what the backend
# needs — ffmpeg (for decoding non-WAV audio) and the Python venv with deps.
# Safe to re-run; each step is a no-op if already satisfied.
set -uo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
BACKEND="$REPO_ROOT/backend"

# 1. ffmpeg
if ! command -v ffmpeg >/dev/null 2>&1; then
  echo "[session-start] installing ffmpeg..."
  (sudo apt-get update -y && sudo apt-get install -y ffmpeg) >/dev/null 2>&1 \
    || (apt-get update -y && apt-get install -y ffmpeg) >/dev/null 2>&1 \
    || echo "[session-start] WARN: could not install ffmpeg (non-WAV decoding will fail)"
fi

# 2. Python venv + dependencies
if [ ! -d "$BACKEND/.venv" ]; then
  echo "[session-start] creating backend venv + installing deps (this can take a few minutes)..."
  python3 -m venv "$BACKEND/.venv"
  # shellcheck disable=SC1091
  source "$BACKEND/.venv/bin/activate"
  pip install --quiet --upgrade pip wheel "setuptools<81"
  pip install --quiet -r "$BACKEND/requirements.txt" \
    || echo "[session-start] WARN: backend dependency install failed"
fi

echo "[session-start] backend ready. Run: source backend/.venv/bin/activate && uvicorn app.main:app --reload (from backend/)"
exit 0
