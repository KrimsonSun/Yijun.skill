# shellcheck shell=bash
# Tiny logging helpers used by every orchestrator script.
# Usage: source "$(dirname "$0")/lib/log.sh"

if [ -t 1 ]; then
    LOG_DIM=$'\033[2m'
    LOG_RED=$'\033[31m'
    LOG_GREEN=$'\033[32m'
    LOG_YELLOW=$'\033[33m'
    LOG_CYAN=$'\033[36m'
    LOG_BOLD=$'\033[1m'
    LOG_RESET=$'\033[0m'
else
    LOG_DIM=""; LOG_RED=""; LOG_GREEN=""; LOG_YELLOW=""; LOG_CYAN=""; LOG_BOLD=""; LOG_RESET=""
fi

LOG_PREFIX="${LOG_PREFIX:-orch}"

_log() {
    local level="$1"; shift
    local color="$1"; shift
    printf '%s[%s] %-5s%s %s\n' "$color" "$LOG_PREFIX" "$level" "$LOG_RESET" "$*" >&2
}

log_info()  { _log INFO  "$LOG_CYAN"   "$@"; }
log_ok()    { _log OK    "$LOG_GREEN"  "$@"; }
log_warn()  { _log WARN  "$LOG_YELLOW" "$@"; }
log_error() { _log ERROR "$LOG_RED"    "$@"; }
log_step()  { printf '\n%s━━━ %s ━━━%s\n' "$LOG_BOLD" "$*" "$LOG_RESET" >&2; }

die() {
    log_error "$@"
    exit 1
}
