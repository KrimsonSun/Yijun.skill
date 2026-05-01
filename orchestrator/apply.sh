#!/usr/bin/env bash
# apply.sh — manual-gate: drop the bundle into Emma on a per-iteration branch.
#
# Per the plan, this is the ONE step that always asks for human approval
# (unless YIJUN_YES_APPLY=1 is exported, e.g. for CI). Everything else in the
# orchestrator is unattended.
#
# Inputs:
#   --emma-path     local Emma_EmotionsAssistant checkout
#   --bundle        path to a rendered bundle (output of emit.sh)
#   --run-id        e.g. 2026-04-30T19-00
#   --iter          iteration number
#
# Behavior:
#   1. Asserts Emma working tree is clean
#   2. Creates branch yijun-skill/iter-<N> from origin/main
#   3. Maps bundle files into Emma's tree
#   4. Computes a unified diff vs origin/main
#   5. Prompts y/N/d at the gate (skip prompt if YIJUN_YES_APPLY=1)
#   6. On y: git add + commit on the iter branch
#   7. On N: deletes the iter branch and exits 2 (the orchestrator stops)

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SKILL_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

# shellcheck source=lib/log.sh
source "$SCRIPT_DIR/lib/log.sh"
# shellcheck source=lib/git-ops.sh
source "$SCRIPT_DIR/lib/git-ops.sh"
LOG_PREFIX="apply"

EMMA_PATH=""
BUNDLE=""
RUN_ID=""
ITER=""

while [[ $# -gt 0 ]]; do
    case "$1" in
        --emma-path) EMMA_PATH="$2"; shift 2 ;;
        --bundle)    BUNDLE="$2"; shift 2 ;;
        --run-id)    RUN_ID="$2"; shift 2 ;;
        --iter)      ITER="$2"; shift 2 ;;
        *)           die "Unknown arg: $1" ;;
    esac
done

[ -n "$EMMA_PATH" ] || die "--emma-path required"
[ -n "$BUNDLE" ]    || die "--bundle required"
[ -n "$RUN_ID" ]    || die "--run-id required"
[ -n "$ITER" ]      || die "--iter required"

[ -d "$BUNDLE" ] || die "bundle not found: $BUNDLE"

assert_git_repo "$EMMA_PATH"
assert_clean_worktree "$EMMA_PATH"

BRANCH="yijun-skill/$RUN_ID/iter-$ITER"
log_step "Apply iter-$ITER on $BRANCH"

# 1. Branch
emma_iter_branch "$EMMA_PATH" "$BRANCH"

# 2. Map bundle files into Emma's tree
log_info "Mapping bundle into Emma working tree"

# 2a. system-prompt.md → backend/persona/system-prompt.md (new path; consumed by llm_service)
mkdir -p "$EMMA_PATH/backend/persona"
cp "$BUNDLE/system-prompt.md" "$EMMA_PATH/backend/persona/system-prompt.md"

# 2b. Each plugin folder maps into Emma based on its manifest pattern:
#     - server-snippet.py    → backend/mcp/plugins/<id>.py        (or backend/games/<id>/tools.py for games)
#     - routes-snippet.py    → backend/api/routes/<id>_ws.py      (or backend/api/routes/<id>.py for games)
#     - realtime-snippet.py  → backend/realtime.py                (shared infra, only landed once)
#     - frontend-snippet.jsx → emitted as a .patch under backend/persona/_pending/  (NOT auto-merged into Live2DViewer.jsx)
#     - GamePanel.jsx        → frontend/src/components/games/<Id>Panel.jsx
#     - game.css             → frontend/src/styles/<id>.css

mkdir -p "$EMMA_PATH/backend/mcp/plugins" \
         "$EMMA_PATH/backend/api/routes" \
         "$EMMA_PATH/backend/games" \
         "$EMMA_PATH/backend/persona/_pending" \
         "$EMMA_PATH/frontend/src/components/games" \
         "$EMMA_PATH/frontend/src/styles"

REALTIME_LANDED=0
for plugin_dir in "$BUNDLE"/plugins/*/; do
    [ -d "$plugin_dir" ] || continue
    plugin_name="$(basename "$plugin_dir")"
    manifest="$plugin_dir/manifest.json"
    [ -f "$manifest" ] || { log_warn "skip $plugin_name (no manifest)"; continue; }
    plugin_id="$(python -c "import json,sys; print(json.load(open(sys.argv[1], encoding='utf-8'))['id'])" "$manifest")"

    log_info "  · $plugin_id"

    # MCP-style plugin (live2d): server / routes / realtime
    if [ -f "$plugin_dir/server-snippet.py" ]; then
        if [ "$plugin_id" = "live2d" ]; then
            cp "$plugin_dir/server-snippet.py" "$EMMA_PATH/backend/mcp/plugins/${plugin_id}.py"
        else
            mkdir -p "$EMMA_PATH/backend/games/${plugin_id}"
            cp "$plugin_dir/mcp-tools.py" "$EMMA_PATH/backend/games/${plugin_id}/tools.py"
            cp "$plugin_dir/manifest.json" "$EMMA_PATH/backend/games/${plugin_id}/manifest.json"
        fi
    fi
    # Game plugin (monopoly): mcp-tools.py
    if [ -f "$plugin_dir/mcp-tools.py" ] && [ "$plugin_id" != "live2d" ]; then
        mkdir -p "$EMMA_PATH/backend/games/${plugin_id}"
        cp "$plugin_dir/mcp-tools.py" "$EMMA_PATH/backend/games/${plugin_id}/tools.py"
        cp "$plugin_dir/manifest.json" "$EMMA_PATH/backend/games/${plugin_id}/manifest.json"
        [ -f "$plugin_dir/state.schema.json" ] && cp "$plugin_dir/state.schema.json" "$EMMA_PATH/backend/games/${plugin_id}/state.schema.json"
    fi
    # Routes
    if [ -f "$plugin_dir/routes-snippet.py" ]; then
        cp "$plugin_dir/routes-snippet.py" "$EMMA_PATH/backend/api/routes/${plugin_id}_orch.py"
    fi
    # Realtime infra — shared, land at most once per apply
    if [ -f "$plugin_dir/realtime-snippet.py" ] && [ "$REALTIME_LANDED" = "0" ]; then
        cp "$plugin_dir/realtime-snippet.py" "$EMMA_PATH/backend/realtime.py"
        REALTIME_LANDED=1
    fi
    # Frontend snippet — kept as a pending patch since Live2DViewer.jsx needs surgical merge
    if [ -f "$plugin_dir/frontend-snippet.jsx" ]; then
        cp "$plugin_dir/frontend-snippet.jsx" \
           "$EMMA_PATH/backend/persona/_pending/${plugin_id}-frontend-snippet.jsx"
    fi
    # Game UI files
    if [ -f "$plugin_dir/GamePanel.jsx" ]; then
        # PascalCase the id
        comp="$(python -c "import sys; s=sys.argv[1]; print(s[:1].upper()+s[1:].lower()+'Panel.jsx')" "$plugin_id")"
        cp "$plugin_dir/GamePanel.jsx" "$EMMA_PATH/frontend/src/components/games/${comp}"
    fi
    if [ -f "$plugin_dir/game.css" ]; then
        cp "$plugin_dir/game.css" "$EMMA_PATH/frontend/src/styles/${plugin_id}.css"
    fi
done

# 2c. Playwright tests — into eval/ inside Emma so docker-compose ports
#     are reachable from the test runner.
mkdir -p "$EMMA_PATH/eval/tests" "$EMMA_PATH/eval/fixtures"
cp -r "$BUNDLE/playwright/tests/."    "$EMMA_PATH/eval/tests/"
cp -r "$BUNDLE/playwright/fixtures/." "$EMMA_PATH/eval/fixtures/"
cp    "$BUNDLE/playwright/playwright.config.ts" "$EMMA_PATH/eval/playwright.config.ts"
cp    "$BUNDLE/playwright/package.json"          "$EMMA_PATH/eval/package.json"

# 3. Diff vs origin/main
DIFF_PATH="$BUNDLE/../emma-diff.patch"
git -C "$EMMA_PATH" add -A
git -C "$EMMA_PATH" diff --cached --stat origin/main > "$BUNDLE/../emma-diff.summary.txt"
git -C "$EMMA_PATH" diff --cached origin/main > "$DIFF_PATH"

DIFF_LINES=$(wc -l < "$DIFF_PATH" | tr -d ' ')
SUMMARY=$(cat "$BUNDLE/../emma-diff.summary.txt")

log_step "Apply gate — review the diff"
echo
echo "$SUMMARY"
echo
log_info "Full diff: $DIFF_PATH ($DIFF_LINES lines)"
log_info "Validation checklist: $SCRIPT_DIR/prompts/apply-validate-checklist.md"
echo

# 4. Gate
ANSWER="${YIJUN_YES_APPLY:-}"
if [ "$ANSWER" = "1" ]; then
    log_warn "YIJUN_YES_APPLY=1 — skipping interactive prompt"
    ANSWER="y"
fi

while [ -z "${ANSWER:-}" ]; do
    printf '%s[apply] Apply this iteration to %s? [y/N/d=show diff/c=show checklist] %s' \
        "$LOG_BOLD" "$BRANCH" "$LOG_RESET" >&2
    read -r raw
    case "${raw,,}" in
        y|yes)       ANSWER="y" ;;
        n|no|"")     ANSWER="n" ;;
        d|diff)      ${PAGER:-less} "$DIFF_PATH" ;;
        c|checklist) ${PAGER:-less} "$SCRIPT_DIR/prompts/apply-validate-checklist.md" ;;
        *)           log_warn "unrecognized input '$raw'" ;;
    esac
done

if [ "$ANSWER" = "n" ]; then
    log_warn "User declined apply — rolling back iter branch"
    git -C "$EMMA_PATH" reset --hard origin/main --quiet
    git -C "$EMMA_PATH" checkout main --quiet
    git -C "$EMMA_PATH" branch -D "$BRANCH" --quiet
    exit 2
fi

# 5. Commit
git -C "$EMMA_PATH" commit -m "yijun-distill iter-$ITER (run $RUN_ID)

Bundle: $BUNDLE
Skill SHA: $(git -C "$SKILL_ROOT" rev-parse --short HEAD 2>/dev/null || echo no-git)

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>" --quiet

log_ok "Committed iter-$ITER on $BRANCH"
echo "$BRANCH"
