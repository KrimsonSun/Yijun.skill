# Orchestrator — operator's manual

The orchestrator turns the `yijun-distill` skill from a static scaffold into a self-iterating loop. It reaches into Emma over the filesystem, runs each iteration on a per-iteration branch, and stops when the rubric passes or max iterations hit.

> **One-line summary:** `bash iterate.sh --emma-path ~/dev/Emma_EmotionsAssistant --max-iters 5`

## Architecture

```
iterate.sh                     — top-level entry; parses args, loops, logs
└── orchestrator/
    ├── distill.sh             — phase 1 (auto, headless Claude; cached on Emma SHA)
    ├── emit.sh                — phase 2 (pure bash + Python; renders bundle)
    ├── apply.sh               — phase 3 (manual gate; branch ops; copies into Emma)
    ├── eval.sh                — phase 4 (auto; wraps eval/run.sh)
    ├── decide-patch.sh        — phase 5 (auto, headless Claude; only on failure)
    ├── lib/
    │   ├── log.sh             — colored log helpers
    │   ├── git-ops.sh         — branch / SHA helpers
    │   └── prompt.py          — system-prompt template renderer
    └── prompts/
        ├── apply-validate-checklist.md   — what user reviews at apply gate
        ├── distill-headless.md           — instructions for Claude in distill phase
        └── decide-patch-headless.md      — instructions for Claude in patch phase
```

## Common runs

### First run — try one iteration end-to-end

```bash
bash iterate.sh \
    --emma-path ~/dev/Emma_EmotionsAssistant \
    --max-iters 1
```

This runs distill (cached if Emma main SHA hasn't moved) → emit → apply (asks `y/N/d`) → eval → report. After it finishes:

```bash
ls output/runs/$(ls -t output/runs | head -1)/iter-1/
# bundle/  emma-diff.patch  eval-report.md  ...
```

### Dry-run — emit only, never touch Emma

```bash
bash iterate.sh --dry-run
```

Useful for sanity-checking the bundle structure before letting it touch a real Emma checkout.

### Auto-iterate up to 5 times — until rubric passes or budget exhausted

```bash
bash iterate.sh \
    --emma-path ~/dev/Emma_EmotionsAssistant \
    --max-iters 5 \
    --threshold 0.85
```

Each iteration:
1. Renders a fresh bundle from current `Yijun.skill/` state (which `decide-patch.sh` may have edited based on the previous iter's report)
2. Asks you to approve apply
3. Runs Playwright
4. If failed and not at `--max-iters`: hands the report to a headless Claude that edits the smallest unit in `Yijun.skill/` and commits to `auto-iter/<run-id>`
5. Loops

### Apply-only (no eval yet) — useful before P2 lands or for first manual run

```bash
bash iterate.sh --emma-path ~/dev/Emma_EmotionsAssistant --max-iters 1 --no-eval
```

### Eval-only manual loop — disable auto-patch

```bash
bash iterate.sh --emma-path ~/dev/Emma_EmotionsAssistant --max-iters 1 --no-decide-patch
```

The orchestrator stops after the first failed eval; you decide what to fix in `Yijun.skill/` and re-run.

## Phases in detail

### Phase 1 — Distill (auto, optional)

Reads Emma's `main` branch on GitHub. If `claude` CLI isn't on PATH, this phase is skipped and the loop uses whatever `distill/*.md` is committed. If Emma's `main` SHA matches the cached one in `output/last-distill-sha`, the call is skipped (cache hit).

When it runs, Claude regenerates `distill/persona.md`, `aesthetic.md`, `stack.md` and logs any drift to `output/runs/<run>/distill-drift.md`. Commits land on `auto-iter/<run-id>`.

### Phase 2 — Emit (auto)

Pure bash + Python. `orchestrator/lib/prompt.py` renders `prompts/system-prompt.template.md` against the current distillates. Plugins and Playwright tests are copied verbatim. Output: `output/runs/<run>/iter-<N>/bundle/`.

### Phase 3 — Apply (MANUAL GATE)

Creates `yijun-skill/<run>/iter-<N>` from `origin/main` in Emma. Copies bundle files into Emma's tree following the mapping defined in `apply.sh`. Prints a diff summary and asks `y/N/d/c`. Bypass with `YIJUN_YES_APPLY=1` (CI only — defaults off).

Some Emma edits are intentionally left manual (route registration in `main.py`, MCP plugin registration, `Live2DViewer.jsx` snippet merge). The `apply-validate-checklist.md` lists them. Skipping these manual steps means eval will fail.

### Phase 4 — Eval (auto)

Boots Emma docker-compose, runs Playwright in `Emma/eval/`, copies the resulting `eval-report.md` into `output/runs/<run>/iter-<N>/`. Aggregate score is parsed from the report's last row.

### Phase 5 — Decide-patch (auto, only on failure)

Hands the report to a headless Claude with strict instructions: edit the **smallest** unit in `Yijun.skill/` that should fix the failing dimension. Commit to `auto-iter/<run-id>`. Next iteration's emit picks it up.

If Claude determines the failure needs human action (Emma not wired up correctly, etc.), it writes `decision.md` and exits non-zero — orchestrator halts.

## Branch hygiene

| Repo | Branches it creates |
|---|---|
| `Emma_EmotionsAssistant` | `yijun-skill/<run-id>/iter-1`, `yijun-skill/<run-id>/iter-2`, ... |
| `Yijun.skill` | `auto-iter/<run-id>` |

Neither repo's `main` is ever touched by the orchestrator. After a passing run, you get a printed merge command — running it is the only way changes land on Emma's `main`.

## Cleaning up old runs

```bash
# Drop iter branches older than the last 5 runs in Emma
cd ~/dev/Emma_EmotionsAssistant
git branch | grep yijun-skill | head -n -10 | xargs -r git branch -D

# Drop auto-iter branches older than last 5 in skill repo
cd /path/to/Yijun.skill
git branch | grep auto-iter | head -n -5 | xargs -r git branch -D

# Drop output runs (gitignored, but disk grows)
rm -rf output/runs/2026-01* 2026-02*
```

## Cost ceiling

Each `iterate.sh` invocation makes at most:
- 1 headless Claude call for distill (or 0 if cached / CLI absent)
- N–1 headless Claude calls for decide-patch, where N = `--max-iters`

`--max-iters=5` caps total Claude calls at ~6. Passing on iter-1 caps at 1 (just distill). The bound is predictable.

## Troubleshooting

| Symptom | Likely cause | Fix |
|---|---|---|
| `apply.sh` fails with "Working tree dirty" | Emma has uncommitted work | Commit / stash in Emma first |
| Branch already exists error | Previous run died mid-flight | `cd Emma && git branch -D yijun-skill/<run>/iter-N` |
| Eval phase exits with rc=2 | `eval/playwright.config.ts` missing in Emma | Apply was incomplete — check `_pending/` and the manual wiring steps in `apply-validate-checklist.md` |
| `aggregate` parse warning | self-eval.spec.ts didn't run to completion | Check `output/runs/<run>/iter-<N>/playwright.log` |
| Decide-patch loops forever editing the same file | A failure dimension isn't actually fixable from the skill side | Pass `--no-decide-patch`, fix manually, re-run |
| `claude binary not found` | Claude Code CLI not on PATH | Set `CLAUDE_BIN=/path/to/claude` or install Claude Code |

## What the orchestrator deliberately does NOT do

- **Auto-merge to Emma `main`**: always requires a human `git merge` command
- **Auto-push** any branch to remote
- **Edit Emma source files outside of bundle-mapped paths**
- **Lower a rubric threshold** to make a test pass
- **Add a new persona** to escape a failure on the existing one
- **Touch `update-prompts.sql`**: persona is sourced from `distill/persona.md` now; `init-characters.sh` will be rewritten by hand to read from there
