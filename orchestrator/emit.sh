#!/usr/bin/env bash
# emit.sh — render the bundle for one iteration.
#
# Inputs:
#   --skill-root   path to Yijun.skill (defaults to script's repo)
#   --run-dir      e.g. output/runs/2026-04-30T19-00/
#   --iter         iteration number (1-based)
#   --character    persona id (default emma)
#   --games        comma-separated game ids (default monopoly)
#
# Outputs:
#   <run-dir>/iter-<N>/bundle/system-prompt.md
#   <run-dir>/iter-<N>/bundle/plugins/...
#   <run-dir>/iter-<N>/bundle/playwright/...
#   <run-dir>/iter-<N>/bundle/manifest.json     (records what was rendered)

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SKILL_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

# shellcheck source=lib/log.sh
source "$SCRIPT_DIR/lib/log.sh"
LOG_PREFIX="emit"

CHARACTER="emma"
GAMES="monopoly"
RUN_DIR=""
ITER=""

while [[ $# -gt 0 ]]; do
    case "$1" in
        --skill-root) SKILL_ROOT="$2"; shift 2 ;;
        --run-dir)    RUN_DIR="$2"; shift 2 ;;
        --iter)       ITER="$2"; shift 2 ;;
        --character)  CHARACTER="$2"; shift 2 ;;
        --games)      GAMES="$2"; shift 2 ;;
        *)            die "Unknown arg: $1" ;;
    esac
done

[ -n "$RUN_DIR" ] || die "--run-dir required"
[ -n "$ITER" ]    || die "--iter required"

BUNDLE_DIR="$RUN_DIR/iter-$ITER/bundle"
mkdir -p "$BUNDLE_DIR/plugins" "$BUNDLE_DIR/playwright/tests" "$BUNDLE_DIR/playwright/fixtures"

log_step "Emit iter-$ITER → $BUNDLE_DIR"

# 1. Render system prompt
log_info "Rendering system-prompt.md (character=$CHARACTER, games=$GAMES)"
python "$SCRIPT_DIR/lib/prompt.py" \
    --skill-root "$SKILL_ROOT" \
    --character "$CHARACTER" \
    --games "$GAMES" \
    --output "$BUNDLE_DIR/system-prompt.md" >/dev/null

# 2. Copy plugins. Each plugin is dropped as-is so apply.sh can map files
#    into Emma's tree based on each plugin's manifest.
for plugin_id in $(echo "$GAMES,live2d" | tr ',' '\n' | sort -u); do
    [ -z "$plugin_id" ] && continue
    src=""
    if [ -d "$SKILL_ROOT/plugins/${plugin_id}-game" ]; then
        src="$SKILL_ROOT/plugins/${plugin_id}-game"
    elif [ -d "$SKILL_ROOT/plugins/${plugin_id}-mcp" ]; then
        src="$SKILL_ROOT/plugins/${plugin_id}-mcp"
    fi
    [ -z "$src" ] && continue
    log_info "  · copying plugin $plugin_id from $src"
    cp -r "$src" "$BUNDLE_DIR/plugins/"
done

# 3. Copy Playwright eval into bundle so apply.sh can drop it into the
#    user's eval/ inside Emma's branch (kept under Emma so docker-compose
#    sees test fixtures co-located).
log_info "Copying Playwright eval"
cp -r "$SKILL_ROOT/eval/tests/."     "$BUNDLE_DIR/playwright/tests/"
cp -r "$SKILL_ROOT/eval/fixtures/."  "$BUNDLE_DIR/playwright/fixtures/"
cp    "$SKILL_ROOT/eval/playwright.config.ts" "$BUNDLE_DIR/playwright/"
cp    "$SKILL_ROOT/eval/package.json"         "$BUNDLE_DIR/playwright/"

# 4. Bundle manifest — records exactly what landed, for traceability.
SKILL_SHA="$(git -C "$SKILL_ROOT" rev-parse --short HEAD 2>/dev/null || echo "no-git")"
cat > "$BUNDLE_DIR/manifest.json" <<EOF
{
  "iter": $ITER,
  "skill_sha": "$SKILL_SHA",
  "character": "$CHARACTER",
  "games": "$GAMES",
  "rendered_at": "$(date -u +%Y-%m-%dT%H:%M:%SZ)",
  "files": {
    "system_prompt": "system-prompt.md",
    "plugins": "plugins/",
    "playwright": "playwright/"
  }
}
EOF

log_ok "Bundle ready: $BUNDLE_DIR"
echo "$BUNDLE_DIR"
