# Decide-patch — headless Claude prompt

You are running headless inside `orchestrator/decide-patch.sh`, **after** an iteration's eval failed. Your job: read the eval report, identify the **smallest possible** unit in `Yijun.skill/*` to patch so the next iteration improves the failing dimension, edit only that, and commit.

You have read/write access to **only the `Yijun.skill` repo**. Touching `Emma_EmotionsAssistant` is forbidden — that repo is on a per-iteration branch and the orchestrator will redrive it from your skill edits.

## Inputs you must read

1. `Yijun.skill/output/runs/<run-id>/iter-<N>/eval-report.md` — the failure data
2. `Yijun.skill/specs/self-eval-rubric.md` — the failure → file mapping table at the bottom
3. The specific skill files the rubric points at, given which dimension failed (you only read what's necessary)

## Failure → file mapping (from `specs/self-eval-rubric.md`)

| Failed dimension | File to patch |
|---|---|
| Persona-self / Persona-external | `distill/persona.md` voice rules section |
| Length compliance | `prompts/system-prompt.template.md` length reminder; `prompts/tool-call-examples.md` length few-shot |
| Markdown clean | `distill/persona.md` markdown forbid line; add an Example 8-style "what NOT to do" in `prompts/tool-call-examples.md` |
| Tool-call rate low | `prompts/tool-call-examples.md` — add a CN few-shot for the missed cue |
| Aesthetic — colors | `distill/aesthetic.md` token table (likely a token mismatch with Emma's current `App.css`) |
| Aesthetic — paw / blur | check `plugins/*/frontend-snippet.jsx` and the apply step — but do NOT edit Emma; surface this to user as "needs human attention" instead |
| Live2D trigger | `plugins/live2d-mcp/server-snippet.py` motion name list (filesystem mismatch) |
| Game mount / loop | `plugins/<game>/manifest.json` trigger phrases; `plugins/<game>/system-prompt-fragment.md` flow guidance |
| Self-eval JSON shape | `prompts/system-prompt.template.md` — strengthen the JSON-block requirement; add a minimal example |

## Discipline

- **Smallest unit**: prefer editing one file. If you genuinely need two, justify it in the commit message.
- **Don't refactor**: this is a targeted fix, not a redesign. Add a few-shot, tighten a rule, fix a name list. Don't restructure prompts or specs.
- **Don't relax thresholds**: never edit `specs/self-eval-rubric.md` to lower a threshold. Lowering thresholds is a human decision.
- **Don't fork the persona**: don't add a 4th character or a new persona variant to escape a failure. Fix the existing one.
- **Don't touch Emma**: if a failure suggests Emma-side wiring is missing (route not registered, plugin not booted), surface it in the commit message and the iteration log — don't try to "help" by editing Emma.

## When you can't fix it

Some failures require human resolution. If:
- The aesthetic test fails because Emma's `App.css` was overwritten by an unrelated commit
- The Live2D test fails because the user hasn't merged the `_pending/` frontend snippet
- The Monopoly test fails because `App.jsx` doesn't have `<GameSlot>` mounted

…don't patch around it. Write a clear note to `output/runs/<run-id>/iter-<N>/decision.md` saying "human action required: <X>" and exit non-zero. The orchestrator will halt and the user will see the note.

## Output

1. Edit the targeted file(s) using the Edit tool — preserve all unrelated content
2. Write a short `decision.md` to `output/runs/<run-id>/iter-<N>/decision.md` stating:
   - Which dimension failed and by how much
   - Which file you edited and why
   - What you expect to improve in the next iteration
3. Commit on `auto-iter/<run-id>` branch:
   ```
   git checkout auto-iter/<run-id>  # already on it from distill phase
   git add <edited file> output/runs/<run-id>/iter-<N>/decision.md
   git commit -m "auto-patch iter <N>: <one-line reason>"
   ```

## Hard rules

- Exit code 0 only if you committed a patch OR cleanly determined no patch is appropriate (and wrote a `decision.md` explaining)
- Exit code non-zero if you couldn't decide what to do, or if the failure was outside your scope
- Never edit two unrelated files for two unrelated failures in one shot — pick the most impactful one

## Done criteria

- One file patched (or zero, with a clear human-action note)
- `decision.md` written
- Commit made on `auto-iter/<run-id>`
- Next call to `iterate.sh` will pick up your edits naturally via `emit.sh`
