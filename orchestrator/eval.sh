#!/usr/bin/env bash
# eval.sh — boot Emma, run Playwright, parse the report, copy it into the run dir.
#
# Wraps the existing eval/run.sh (which lives inside Emma after apply lands its
# eval/ tree). This wrapper differs from a direct run.sh call only in: it knows
# where to drop the resulting eval-report.md so iterate.sh can read it back.
#
# Inputs:
#   --emma-path   local Emma checkout
#   --skill-root  Yijun.skill root
#   --run-dir     output/runs/<run>
#   --iter        iteration number
#
# Exit codes:
#   0  — eval ran AND aggregate >= threshold
#   1  — eval ran but aggregate < threshold (Playwright reported failures)
#   2  — eval couldn't run (Emma didn't come up, no tests, etc.)

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# shellcheck source=lib/log.sh
source "$SCRIPT_DIR/lib/log.sh"
LOG_PREFIX="eval"

EMMA_PATH=""
SKILL_ROOT=""
RUN_DIR=""
ITER=""

while [[ $# -gt 0 ]]; do
    case "$1" in
        --emma-path)  EMMA_PATH="$2"; shift 2 ;;
        --skill-root) SKILL_ROOT="$2"; shift 2 ;;
        --run-dir)    RUN_DIR="$2"; shift 2 ;;
        --iter)       ITER="$2"; shift 2 ;;
        *)            die "Unknown arg: $1" ;;
    esac
done

[ -n "$EMMA_PATH" ] && [ -n "$RUN_DIR" ] && [ -n "$ITER" ] || die "missing required args"

ITER_DIR="$RUN_DIR/iter-$ITER"
mkdir -p "$ITER_DIR"

log_step "Eval iter-$ITER"

# 1. Ensure Emma's eval/ has what it needs — apply.sh should have copied the
#    fixtures and config in. If not, the user skipped the manual main.py
#    wiring or apply was declined; bail with rc=2.
if [ ! -f "$EMMA_PATH/eval/playwright.config.ts" ]; then
    log_error "Emma's eval/ doesn't have playwright.config.ts — apply may have been incomplete"
    exit 2
fi

# 2. Bring Emma up
EMMA_API="${EMMA_API_BASE:-http://localhost:8000}"
EMMA_URL="${EMMA_URL:-http://localhost:5173}"

if ! curl -sf "$EMMA_API/" >/dev/null 2>&1 \
   && ! curl -sf "$EMMA_API/health" >/dev/null 2>&1 \
   && ! curl -sf "$EMMA_API/api/health" >/dev/null 2>&1; then
    log_info "Bringing Emma up via docker-compose"
    if ! (cd "$EMMA_PATH" && docker-compose up -d); then
        log_error "docker-compose failed"
        exit 2
    fi

    log_info "Waiting for backend at $EMMA_API"
    for i in $(seq 1 60); do
        if curl -sf "$EMMA_API/" >/dev/null 2>&1 \
           || curl -sf "$EMMA_API/health" >/dev/null 2>&1 \
           || curl -sf "$EMMA_API/api/health" >/dev/null 2>&1; then
            log_ok "backend responding (after ${i}s)"
            break
        fi
        sleep 1
    done
fi

# 3. Install Playwright deps if missing
cd "$EMMA_PATH/eval"
if [ ! -d "node_modules" ]; then
    log_info "Installing Playwright"
    npm install --silent
    npx playwright install chromium
fi

# 4. Run tests; capture exit code (don't fail the script — we want the report
#    even on failure)
log_info "Running Playwright suite"
EVAL_RC=0
EMMA_URL="$EMMA_URL" EMMA_API_BASE="$EMMA_API" \
    npx playwright test --reporter=list,html,json \
    > "$ITER_DIR/playwright.log" 2>&1 || EVAL_RC=$?

# 5. The self-eval.spec.ts writes eval-report.md into Yijun.skill/output/bundle-*/.
#    Find the most recent and copy into iter-$ITER/.
cd "$SCRIPT_DIR/.."
LATEST_REPORT=$(find output -name 'eval-report.md' -type f -printf '%T@ %p\n' 2>/dev/null \
                | sort -n | tail -1 | cut -d' ' -f2- || true)

if [ -z "$LATEST_REPORT" ] || [ ! -f "$LATEST_REPORT" ]; then
    log_error "no eval-report.md produced — Playwright may have crashed before self-eval.spec ran"
    cp "$ITER_DIR/playwright.log" "$ITER_DIR/eval-report.md" 2>/dev/null || true
    exit 2
fi

cp "$LATEST_REPORT" "$ITER_DIR/eval-report.md"
log_info "Report: $ITER_DIR/eval-report.md"

# 6. Parse aggregate score
AGGREGATE=$(grep -E '^\| \*\*Aggregate\*\*' "$ITER_DIR/eval-report.md" 2>/dev/null \
    | awk -F'|' '{gsub(/[ *]/,"",$3); print $3}' || echo "0")

if [ -z "$AGGREGATE" ]; then
    log_warn "could not parse aggregate score from report"
    exit 2
fi

log_info "Aggregate: $AGGREGATE"

# 7. Decide pass/fail. The threshold check actually lives in
#    self-eval.spec.ts (the test fails if aggregate < 0.80), so EVAL_RC
#    already reflects pass/fail. But re-check the report to be safe.
if [ "$EVAL_RC" = "0" ]; then
    log_ok "Eval passed"
    exit 0
else
    log_warn "Eval failed"
    exit 1
fi
