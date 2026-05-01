#!/usr/bin/env bash
# distill.sh — re-extract Emma's persona / aesthetic / stack from GitHub
# into Yijun.skill/distill/. Wraps a headless Claude call.
#
# Cached on Emma's main SHA: if SHA hasn't changed since last successful run,
# this is a no-op.
#
# Inputs:
#   --skill-root  Yijun.skill root
#   --run-dir     output/runs/<run> (for drift log)
#
# Exit codes:
#   0 — distill done (or cached, nothing to do)
#   1 — Claude failed; iterate.sh will fall back to committed distillates

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# shellcheck source=lib/log.sh
source "$SCRIPT_DIR/lib/log.sh"
# shellcheck source=lib/git-ops.sh
source "$SCRIPT_DIR/lib/git-ops.sh"
LOG_PREFIX="distill"

SKILL_ROOT=""
RUN_DIR=""

while [[ $# -gt 0 ]]; do
    case "$1" in
        --skill-root) SKILL_ROOT="$2"; shift 2 ;;
        --run-dir)    RUN_DIR="$2"; shift 2 ;;
        *)            die "Unknown arg: $1" ;;
    esac
done

[ -n "$SKILL_ROOT" ] && [ -n "$RUN_DIR" ] || die "missing required args"

# Cache: skip if Emma's main SHA matches what we last distilled
EMMA_REPO_URL="https://github.com/KrimsonSun/Emma_EmotionsAssistant.git"
CACHE_FILE="$SKILL_ROOT/output/last-distill-sha"
mkdir -p "$SKILL_ROOT/output"

CURRENT_SHA="$(remote_sha "$EMMA_REPO_URL" main || echo "")"
LAST_SHA="$(cat "$CACHE_FILE" 2>/dev/null || echo "")"

if [ -n "$CURRENT_SHA" ] && [ "$CURRENT_SHA" = "$LAST_SHA" ]; then
    log_ok "Cache hit (Emma main @ ${CURRENT_SHA:0:8}) — skipping distill"
    exit 0
fi

# Find claude binary
CLAUDE_BIN="${CLAUDE_BIN:-$(command -v claude || true)}"
if [ -z "$CLAUDE_BIN" ]; then
    log_warn "claude binary not found — skipping headless distill"
    log_warn "Install Claude Code CLI or set CLAUDE_BIN, then re-run"
    exit 1
fi

PROMPT_FILE="$SCRIPT_DIR/prompts/distill-headless.md"
RUN_ID="$(basename "$RUN_DIR")"

log_step "Distill — headless Claude (Emma main @ ${CURRENT_SHA:0:8})"
log_info "Prompt: $PROMPT_FILE"

# Build the message: the prompt + minimal context (run id, current SHA)
MSG="$(cat "$PROMPT_FILE")

---

Run id: $RUN_ID
Emma main SHA: $CURRENT_SHA
Drift log path: $RUN_DIR/distill-drift.md
Skill root (your workspace): $SKILL_ROOT
"

# --print runs Claude headlessly and exits when done. Output is captured.
# --add-dir lets Claude work inside Yijun.skill only.
mkdir -p "$RUN_DIR"
LOG="$RUN_DIR/distill-headless.log"

set +e
"$CLAUDE_BIN" \
    --print \
    --add-dir "$SKILL_ROOT" \
    --permission-mode acceptEdits \
    "$MSG" \
    > "$LOG" 2>&1
RC=$?
set -e

if [ "$RC" != "0" ]; then
    log_error "headless distill failed (rc=$RC); see $LOG"
    exit 1
fi

# Persist the SHA for next-run cache
echo "$CURRENT_SHA" > "$CACHE_FILE"

log_ok "Distill complete (log: $LOG)"
exit 0
