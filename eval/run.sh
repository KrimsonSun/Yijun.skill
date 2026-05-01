#!/usr/bin/env bash
# Run the full Playwright eval against a local Emma instance.
#
# Usage:
#   EMMA_PATH=~/dev/Emma_EmotionsAssistant bash eval/run.sh
#
# Steps:
#   1. Bring up Emma's docker-compose (skip if already running)
#   2. Wait for the chat API to respond
#   3. Install Playwright deps if missing
#   4. Run the test suite
#   5. Print location of eval-report.md

set -euo pipefail

SKILL_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
EVAL_DIR="$SKILL_DIR/eval"
EMMA_PATH="${EMMA_PATH:-${HOME}/dev/Emma_EmotionsAssistant}"
EMMA_URL="${EMMA_URL:-http://localhost:5173}"
EMMA_API_BASE="${EMMA_API_BASE:-http://localhost:8000}"

echo "[eval] skill dir: $SKILL_DIR"
echo "[eval] emma path: $EMMA_PATH"
echo "[eval] emma url:  $EMMA_URL"

if [ ! -d "$EMMA_PATH" ]; then
  echo "[eval] ERROR: Emma path does not exist: $EMMA_PATH"
  echo "[eval] Set EMMA_PATH to your local Emma_EmotionsAssistant checkout."
  exit 1
fi

# 1. Bring up Emma if not already up
if ! curl -sf "$EMMA_API_BASE/api/health" >/dev/null 2>&1 \
   && ! curl -sf "$EMMA_API_BASE/health" >/dev/null 2>&1 \
   && ! curl -sf "$EMMA_API_BASE/" >/dev/null 2>&1; then
  echo "[eval] Bringing Emma up via docker-compose…"
  (cd "$EMMA_PATH" && docker-compose up -d)
fi

# 2. Wait for backend
echo "[eval] Waiting for backend at $EMMA_API_BASE …"
for i in $(seq 1 60); do
  if curl -sf "$EMMA_API_BASE/" >/dev/null 2>&1 \
     || curl -sf "$EMMA_API_BASE/health" >/dev/null 2>&1 \
     || curl -sf "$EMMA_API_BASE/api/health" >/dev/null 2>&1; then
    echo "[eval] backend responding (after ${i}s)"
    break
  fi
  sleep 1
done

# 3. Install Playwright deps
cd "$EVAL_DIR"
if [ ! -d "node_modules" ]; then
  echo "[eval] Installing Playwright dependencies…"
  npm install
  npx playwright install chromium
fi

# 4. Run tests
echo "[eval] Running Playwright suite…"
EMMA_URL="$EMMA_URL" EMMA_API_BASE="$EMMA_API_BASE" npx playwright test || EVAL_EXIT=$?

# 5. Locate report
REPORT=$(find "$SKILL_DIR/output" -name 'eval-report.md' -type f -printf '%T@ %p\n' 2>/dev/null \
         | sort -n | tail -1 | cut -d' ' -f2- || true)
if [ -n "${REPORT:-}" ]; then
  echo "[eval] Report: $REPORT"
fi

exit "${EVAL_EXIT:-0}"
