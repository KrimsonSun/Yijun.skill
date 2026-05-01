#!/usr/bin/env bash
# decide-patch.sh — read the failing eval report, hand it to a headless Claude,
# let Claude edit the smallest unit in Yijun.skill that should improve next iter.
#
# Inputs:
#   --skill-root  Yijun.skill root
#   --run-dir     output/runs/<run>
#   --iter        which iteration's report to read
#
# Exit codes:
#   0 — patch decided (committed) OR explicit "no patch appropriate, human action required" (also committed as a decision.md)
#   1 — Claude couldn't decide; iterate.sh halts the loop

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# shellcheck source=lib/log.sh
source "$SCRIPT_DIR/lib/log.sh"
LOG_PREFIX="patch"

SKILL_ROOT=""
RUN_DIR=""
ITER=""

while [[ $# -gt 0 ]]; do
    case "$1" in
        --skill-root) SKILL_ROOT="$2"; shift 2 ;;
        --run-dir)    RUN_DIR="$2"; shift 2 ;;
        --iter)       ITER="$2"; shift 2 ;;
        *)            die "Unknown arg: $1" ;;
    esac
done

[ -n "$SKILL_ROOT" ] && [ -n "$RUN_DIR" ] && [ -n "$ITER" ] || die "missing required args"

REPORT="$RUN_DIR/iter-$ITER/eval-report.md"
[ -f "$REPORT" ] || die "no eval report at $REPORT"

CLAUDE_BIN="${CLAUDE_BIN:-$(command -v claude || true)}"
if [ -z "$CLAUDE_BIN" ]; then
    log_warn "claude binary not found — cannot decide patch headlessly"
    log_warn "Edit Yijun.skill manually based on $REPORT, commit, then re-run iterate.sh"
    exit 1
fi

PROMPT_FILE="$SCRIPT_DIR/prompts/decide-patch-headless.md"
RUN_ID="$(basename "$RUN_DIR")"

# Make sure we're on auto-iter/<run-id> in Yijun.skill so Claude's commit lands there
CURRENT_BRANCH="$(git -C "$SKILL_ROOT" rev-parse --abbrev-ref HEAD)"
TARGET_BRANCH="auto-iter/$RUN_ID"
if [ "$CURRENT_BRANCH" != "$TARGET_BRANCH" ]; then
    if git -C "$SKILL_ROOT" rev-parse --verify "$TARGET_BRANCH" >/dev/null 2>&1; then
        git -C "$SKILL_ROOT" checkout "$TARGET_BRANCH" --quiet
    else
        git -C "$SKILL_ROOT" checkout -b "$TARGET_BRANCH" --quiet
    fi
fi

log_step "Decide-patch — headless Claude (iter $ITER)"

MSG="$(cat "$PROMPT_FILE")

---

Run id: $RUN_ID
Iter: $ITER
Eval report path: $REPORT
Decision log path: $RUN_DIR/iter-$ITER/decision.md
Skill root (your workspace): $SKILL_ROOT

The current branch in Yijun.skill is $TARGET_BRANCH — commit your patch there.
"

LOG="$RUN_DIR/iter-$ITER/decide-patch-headless.log"

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
    log_error "headless decide-patch failed (rc=$RC); see $LOG"
    exit 1
fi

# Sanity: did Claude actually commit?
if [ -z "$(git -C "$SKILL_ROOT" log --oneline -1 "$TARGET_BRANCH" -- 2>/dev/null)" ]; then
    log_warn "no commit on $TARGET_BRANCH — Claude may have decided no patch was appropriate"
fi

if [ -f "$RUN_DIR/iter-$ITER/decision.md" ]; then
    log_info "Decision: $RUN_DIR/iter-$ITER/decision.md"
fi

log_ok "Patch decided (log: $LOG)"
exit 0
