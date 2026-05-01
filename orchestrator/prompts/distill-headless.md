# Distill — headless Claude prompt

You are running headless inside `orchestrator/distill.sh`. You have read/write access to **only the `Yijun.skill` repo**. You must NOT touch `Emma_EmotionsAssistant`. Your job is one thing: regenerate `distill/persona.md`, `distill/aesthetic.md`, and `distill/stack.md` from the **current state of Emma's `main` branch on GitHub**.

## Inputs you must read

In this order:

1. `https://raw.githubusercontent.com/KrimsonSun/Emma_EmotionsAssistant/main/update-prompts.sql`
2. `https://raw.githubusercontent.com/KrimsonSun/Emma_EmotionsAssistant/main/init-characters.sh`
3. `https://raw.githubusercontent.com/KrimsonSun/Emma_EmotionsAssistant/main/backend/services/llm_service.py`
4. `https://raw.githubusercontent.com/KrimsonSun/Emma_EmotionsAssistant/main/backend/mcp/server.py`
5. `https://raw.githubusercontent.com/KrimsonSun/Emma_EmotionsAssistant/main/frontend/src/App.css`
6. `https://raw.githubusercontent.com/KrimsonSun/Emma_EmotionsAssistant/main/frontend/package.json`
7. `https://raw.githubusercontent.com/KrimsonSun/Emma_EmotionsAssistant/main/backend/requirements.txt` (or `pyproject.toml`)
8. The folder listing at `https://github.com/KrimsonSun/Emma_EmotionsAssistant/tree/main/backend/models/live2d/emma` (read motion `.mtn` and expression `.exp.json` filenames)

## Output rules

You write only these three files (full file rewrite, not patches):

- `Yijun.skill/distill/persona.md`
- `Yijun.skill/distill/aesthetic.md`
- `Yijun.skill/distill/stack.md`

Format and section structure must match the existing files. Read the **current** versions first to understand the shape, then regenerate with new content. Do NOT change the section headers, the file structure, or the heading levels — downstream rendering (`orchestrator/lib/prompt.py`) depends on exact markers like `## Universal voice rules` and `## Emma — 温柔型灵魂伪侣 (default)`.

## Drift detection

Before writing each file, compare the new content to the existing file:

- If **identical**: don't write (avoid pointless commits).
- If **different**: write the new file, AND append a one-line note to `output/runs/<run>/distill-drift.md` describing what changed (e.g., "persona.md — Emma's warmth-marker list gained 摸摸; persona prompt unchanged").

## Hard constraints

- **CN-canonical**: persona blocks stay in Chinese. Do not translate to English. Skill spec docs (other markdown files) stay in English — those are not your concern this phase.
- **Live2D motion names from filesystem only**: do not invent names. If the GitHub tree listing fails, leave the existing motion list in `aesthetic.md` unchanged and log this in `distill-drift.md`.
- **Forbidden substitutions** in `stack.md`: keep the same forbidden list (no TS, no Tailwind, no Next.js, no official `mcp` SDK). If `package.json` shows a forbidden dep was added in Emma upstream, FLAG IT in `distill-drift.md` and refuse to update `stack.md` until human resolves.
- **No edits outside `distill/`**: not `prompts/`, not `specs/`, not `plugins/`. Only the three distillates and the drift log.

## Commit

After writing, commit on the `auto-iter/<run-id>` branch in `Yijun.skill`:

```
git checkout -B auto-iter/<run-id>
git add distill/ output/runs/<run-id>/distill-drift.md
git commit -m "auto-distill iter <N> (run <run-id>)"
```

If nothing changed, exit cleanly without committing.

## What you must NOT do

- Do not edit `Emma_EmotionsAssistant` files — you don't even have the path.
- Do not edit `prompts/`, `specs/`, `plugins/`, `eval/`, `SKILL.md`, or `README.md` in this run.
- Do not run `iterate.sh` recursively.
- Do not push to remote — the orchestrator handles that decision later.

## Done criteria

You're done when either:
1. The three `distill/*.md` files match the current Emma state (some may be unchanged, that's fine), AND
2. Any drift is logged in `output/runs/<run-id>/distill-drift.md`, AND
3. A commit was made on `auto-iter/<run-id>` (or no commit needed because nothing changed).
