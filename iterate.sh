#!/usr/bin/env bash
# iterate.sh — top-level orchestrator for the yijun-distill self-iteration loop.
#
# Usage:
#   bash iterate.sh \
#       --emma-path ~/dev/Emma_EmotionsAssistant \
#       --max-iters 5 \
#       --threshold 0.80 \
#       [--character emma] [--games monopoly] \
#       [--dry-run]            # emit only, no apply / eval / iterate
#       [--no-eval]            # apply but skip eval (useful before P2 lands)
#       [--no-decide-patch]    # eval but don't auto-patch on failure
#
# Phases:
#   1. Distill          (P3 — auto, headless Claude; falls back to committed distillates if unavailable)
#   2. Emit             (P1 — pure bash + Python)
#   3. Apply            (P1 — manual gate, can be bypassed via YIJUN_YES_APPLY=1)
#   4. Eval             (P2 — wraps eval/run.sh)
#   5. Decide-patch     (P3 — headless Claude on eval-report.md; only fires on failure)
#
# Stop conditions:
#   - Aggregate score ≥ threshold (success — prints merge command)
#   - Max iterations reached (failure — leaves all iter branches for inspection)
#   - User declines apply (clean exit)
#   - User Ctrl-C (trapped — current iter branch left intact)

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SKILL_ROOT="$SCRIPT_DIR"

# shellcheck source=orchestrator/lib/log.sh
source "$SCRIPT_DIR/orchestrator/lib/log.sh"
# shellcheck source=orchestrator/lib/git-ops.sh
source "$SCRIPT_DIR/orchestrator/lib/git-ops.sh"
LOG_PREFIX="iter"

EMMA_PATH=""
MAX_ITERS=5
THRESHOLD="0.80"
CHARACTER="emma"
GAMES="monopoly"
DRY_RUN=0
NO_EVAL=0
NO_DECIDE_PATCH=0

while [[ $# -gt 0 ]]; do
    case "$1" in
        --emma-path)        EMMA_PATH="$2"; shift 2 ;;
        --max-iters)        MAX_ITERS="$2"; shift 2 ;;
        --threshold)        THRESHOLD="$2"; shift 2 ;;
        --character)        CHARACTER="$2"; shift 2 ;;
        --games)            GAMES="$2"; shift 2 ;;
        --dry-run)          DRY_RUN=1; shift ;;
        --no-eval)          NO_EVAL=1; shift ;;
        --no-decide-patch)  NO_DECIDE_PATCH=1; shift ;;
        -h|--help)
            sed -n '2,30p' "$0"
            exit 0
            ;;
        *) die "Unknown arg: $1" ;;
    esac
done

# ─── prerequisites ────────────────────────────────────────────────────────

if [ -z "$EMMA_PATH" ] && [ "$DRY_RUN" = "0" ]; then
    die "--emma-path required (or pass --dry-run for emit-only)"
fi

if [ "$DRY_RUN" = "0" ]; then
    EMMA_PATH="$(cd "$EMMA_PATH" && pwd)"
    assert_git_repo "$EMMA_PATH"
    if same_repo "$EMMA_PATH" "$SKILL_ROOT"; then
        die "EMMA_PATH and SKILL_ROOT cannot be the same repo"
    fi
fi

# Cache emma path for future runs
mkdir -p "$HOME/.yijun-skill"
[ -n "$EMMA_PATH" ] && echo "$EMMA_PATH" > "$HOME/.yijun-skill/emma-path"

RUN_ID="$(date -u +%Y-%m-%dT%H-%M-%S)"
RUN_DIR="$SKILL_ROOT/output/runs/$RUN_ID"
mkdir -p "$RUN_DIR"

log_step "Run $RUN_ID"
log_info "Skill root:    $SKILL_ROOT"
log_info "Emma path:     ${EMMA_PATH:-<dry-run>}"
log_info "Character:     $CHARACTER"
log_info "Games:         $GAMES"
log_info "Max iters:     $MAX_ITERS"
log_info "Threshold:     $THRESHOLD"

# Trap SIGINT to flag the current iter branch instead of half-committing
trap 'log_warn "Interrupted — leaving any iter branch in place for inspection"; exit 130' INT TERM

# ─── phase 1: distill (run once before the loop) ──────────────────────────

log_step "Phase 1 — Distill"
if [ -x "$SCRIPT_DIR/orchestrator/distill.sh" ]; then
    bash "$SCRIPT_DIR/orchestrator/distill.sh" \
        --skill-root "$SKILL_ROOT" \
        --run-dir "$RUN_DIR" \
        || log_warn "distill.sh failed (continuing with committed distillates)"
else
    log_info "(distill.sh not present yet — using committed distill/*.md)"
fi

# ─── per-iteration loop ───────────────────────────────────────────────────

FINAL_REPORT="$RUN_DIR/final-report.md"
echo "# Run $RUN_ID — final report" > "$FINAL_REPORT"
echo "" >> "$FINAL_REPORT"
echo "| Iter | Status | Aggregate | Branch | Bundle |" >> "$FINAL_REPORT"
echo "|---|---|---|---|---|" >> "$FINAL_REPORT"

LAST_PASSING_BRANCH=""

for ((ITER=1; ITER<=MAX_ITERS; ITER++)); do
    log_step "Iteration $ITER / $MAX_ITERS"

    # Phase 2 — emit
    BUNDLE="$(bash "$SCRIPT_DIR/orchestrator/emit.sh" \
        --skill-root "$SKILL_ROOT" \
        --run-dir "$RUN_DIR" \
        --iter "$ITER" \
        --character "$CHARACTER" \
        --games "$GAMES" \
        | tail -1)"

    if [ "$DRY_RUN" = "1" ]; then
        echo "| $ITER | dry-run | — | — | $BUNDLE |" >> "$FINAL_REPORT"
        log_ok "dry-run iter-$ITER complete (no apply, no eval)"
        break
    fi

    # Phase 3 — apply (manual gate)
    set +e
    BRANCH="$(bash "$SCRIPT_DIR/orchestrator/apply.sh" \
        --emma-path "$EMMA_PATH" \
        --bundle "$BUNDLE" \
        --run-id "$RUN_ID" \
        --iter "$ITER" \
        | tail -1)"
    APPLY_RC=$?
    set -e

    if [ "$APPLY_RC" = "2" ]; then
        echo "| $ITER | declined | — | — | $BUNDLE |" >> "$FINAL_REPORT"
        log_warn "User declined iter-$ITER — exiting"
        break
    elif [ "$APPLY_RC" != "0" ]; then
        echo "| $ITER | apply-error | — | — | $BUNDLE |" >> "$FINAL_REPORT"
        die "apply.sh failed (rc=$APPLY_RC)"
    fi

    # Phase 4 — eval
    AGGREGATE=""
    EVAL_STATUS="skipped"
    if [ "$NO_EVAL" = "1" ]; then
        log_warn "--no-eval set; skipping eval"
    elif [ -x "$SCRIPT_DIR/orchestrator/eval.sh" ]; then
        if bash "$SCRIPT_DIR/orchestrator/eval.sh" \
            --emma-path "$EMMA_PATH" \
            --skill-root "$SKILL_ROOT" \
            --run-dir "$RUN_DIR" \
            --iter "$ITER"; then
            EVAL_STATUS="pass"
        else
            EVAL_STATUS="fail"
        fi
        REPORT="$RUN_DIR/iter-$ITER/eval-report.md"
        if [ -f "$REPORT" ]; then
            AGGREGATE=$(grep -E '^\| \*\*Aggregate\*\*' "$REPORT" 2>/dev/null \
                | awk -F'|' '{gsub(/[ *]/,"",$3); print $3}' || echo "")
        fi
    else
        log_warn "(eval.sh not present yet — skipping eval phase)"
    fi

    echo "| $ITER | $EVAL_STATUS | ${AGGREGATE:-—} | $BRANCH | $BUNDLE |" >> "$FINAL_REPORT"

    if [ "$EVAL_STATUS" = "pass" ]; then
        LAST_PASSING_BRANCH="$BRANCH"
        log_ok "iter-$ITER passed (aggregate=$AGGREGATE)"
        break
    fi

    if [ "$NO_EVAL" = "1" ] || [ "$EVAL_STATUS" = "skipped" ]; then
        log_info "Skipping decide-patch (no eval ran)"
        break
    fi

    # Phase 5 — decide-patch (only on failure)
    if [ "$NO_DECIDE_PATCH" = "1" ]; then
        log_warn "--no-decide-patch set; halting after first failed eval"
        break
    fi

    if [ "$ITER" = "$MAX_ITERS" ]; then
        log_warn "max-iters reached without pass"
        break
    fi

    if [ -x "$SCRIPT_DIR/orchestrator/decide-patch.sh" ]; then
        log_step "Phase 5 — decide-patch (iter $ITER → $((ITER+1)))"
        bash "$SCRIPT_DIR/orchestrator/decide-patch.sh" \
            --skill-root "$SKILL_ROOT" \
            --run-dir "$RUN_DIR" \
            --iter "$ITER" \
            || { log_warn "decide-patch failed; halting"; break; }
    else
        log_warn "(decide-patch.sh not present yet — halting after first failure)"
        break
    fi
done

# ─── final summary ────────────────────────────────────────────────────────

log_step "Run complete"
echo
cat "$FINAL_REPORT"
echo
log_info "Final report: $FINAL_REPORT"

if [ -n "$LAST_PASSING_BRANCH" ]; then
    log_ok "Passing branch: $LAST_PASSING_BRANCH"
    echo
    echo "  To merge into Emma main:"
    echo "    cd $EMMA_PATH"
    echo "    git checkout main"
    echo "    git merge $LAST_PASSING_BRANCH"
    echo
fi
