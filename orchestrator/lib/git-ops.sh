# shellcheck shell=bash
# Git branch / state helpers for the orchestrator.
# Source this AFTER log.sh.

# Assert the working tree is clean. Fails fast if not — we don't want to
# accidentally commit half-finished user work into an iter branch.
assert_clean_worktree() {
    local repo="$1"
    if [ -n "$(git -C "$repo" status --porcelain)" ]; then
        die "Working tree at $repo is dirty. Commit or stash before iterating."
    fi
}

# Ensure the repo is a git repo at all.
assert_git_repo() {
    local repo="$1"
    [ -d "$repo/.git" ] || git -C "$repo" rev-parse --git-dir >/dev/null 2>&1 \
        || die "Not a git repo: $repo"
}

# Fetch origin/main and check out a new branch from it.
# Idempotent if branch already exists at the right base — otherwise fails so
# we never silently rebase someone else's work.
emma_iter_branch() {
    local repo="$1"
    local branch="$2"
    git -C "$repo" fetch origin main --quiet
    if git -C "$repo" rev-parse --verify "$branch" >/dev/null 2>&1; then
        die "Branch $branch already exists in $repo. Delete it or pick a fresh run id."
    fi
    git -C "$repo" checkout -b "$branch" origin/main --quiet
    log_ok "Created $branch from origin/main"
}

# Get short SHA of the current HEAD in a repo.
short_sha() {
    git -C "$1" rev-parse --short HEAD
}

# Get the latest SHA of a remote ref without cloning.
remote_sha() {
    local url="$1"
    local ref="${2:-main}"
    git ls-remote "$url" "$ref" | awk '{print $1}'
}

# Check whether two paths point to the same git repo (resolves symlinks).
same_repo() {
    [ "$(cd "$1" && pwd -P)" = "$(cd "$2" && pwd -P)" ]
}
