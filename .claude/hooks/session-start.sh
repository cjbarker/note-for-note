#!/usr/bin/env bash
# SessionStart hook: ensure this ephemeral environment has what the backend
# needs — ffmpeg (for decoding non-WAV audio) and the uv-managed Python env.
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

# 2. uv (Python package manager)
if ! command -v uv >/dev/null 2>&1; then
  echo "[session-start] installing uv..."
  pip install --quiet uv >/dev/null 2>&1 \
    || curl -LsSf https://astral.sh/uv/install.sh | sh >/dev/null 2>&1 \
    || echo "[session-start] WARN: could not install uv"
fi

# 3. Sync backend dependencies into the uv-managed venv (.venv).
if command -v uv >/dev/null 2>&1; then
  echo "[session-start] syncing backend deps with uv (first run can take a few minutes)..."
  (cd "$BACKEND" && uv sync) >/dev/null 2>&1 \
    || echo "[session-start] WARN: uv sync failed"
fi

echo "[session-start] backend ready. Run from backend/: uv run uvicorn app.main:app --reload"
exit 0
