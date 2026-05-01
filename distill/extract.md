# Extract — re-distillation playbook

This file tells Claude **how to re-run Phase 1**. Each invocation of the skill starts here. The goal: catch drift between the skill's distillates and Emma's actual current state on GitHub.

---

## Inputs (read in order)

Use WebFetch with the GitHub raw URLs. If a URL 404s, try the GitHub UI URL as fallback (rendering is summarized but still useful).

```
1. https://raw.githubusercontent.com/KrimsonSun/Emma_EmotionsAssistant/main/update-prompts.sql
2. https://raw.githubusercontent.com/KrimsonSun/Emma_EmotionsAssistant/main/init-characters.sh
3. https://raw.githubusercontent.com/KrimsonSun/Emma_EmotionsAssistant/main/backend/services/llm_service.py
4. https://raw.githubusercontent.com/KrimsonSun/Emma_EmotionsAssistant/main/backend/mcp/server.py
5. https://raw.githubusercontent.com/KrimsonSun/Emma_EmotionsAssistant/main/backend/api/routes/chat.py
6. https://raw.githubusercontent.com/KrimsonSun/Emma_EmotionsAssistant/main/backend/api/routes/live2d.py
7. https://raw.githubusercontent.com/KrimsonSun/Emma_EmotionsAssistant/main/frontend/package.json
8. https://raw.githubusercontent.com/KrimsonSun/Emma_EmotionsAssistant/main/frontend/src/App.css
9. https://raw.githubusercontent.com/KrimsonSun/Emma_EmotionsAssistant/main/frontend/src/components/ChatPanel.jsx
10. https://raw.githubusercontent.com/KrimsonSun/Emma_EmotionsAssistant/main/frontend/src/components/Live2DViewer.jsx
11. https://github.com/KrimsonSun/Emma_EmotionsAssistant/tree/main/backend/models/live2d/emma  (HTML page, list motion files)
```

If a local Emma checkout path is cached at `~/.yijun-skill/emma-path`, prefer reading those files via the Read tool — faster and reflects uncommitted changes.

---

## Mappings — what each input drives

| Input | Drives | Conflict resolution |
|---|---|---|
| `update-prompts.sql` | `distill/persona.md` (per-character prompt blocks) | If a persona changed, replace the block verbatim |
| Hardcoded directive in `llm_service.py` (`generate_response`) | `distill/persona.md` "Universal voice rules" section | The directive wins over SQL on tone — Yijun put it in code for a reason |
| `frontend/src/App.css` | `distill/aesthetic.md` (CSS variables, animations, breakpoints) | Verbatim copy of `:root { ... }` block |
| `frontend/package.json` deps | `distill/stack.md` frontend table | Update pinned versions if changed |
| `backend/requirements.txt` (or `pyproject.toml`) | `distill/stack.md` backend table | |
| `backend/mcp/server.py` tool list | `prompts/system-prompt.template.md` `{available_tools}` injection | List tools by name + description |
| `backend/models/live2d/emma/` file listing | `plugins/live2d-mcp/server-snippet.py` motion/expression name arrays | Drop `.mtn` / `.exp.json` names directly |
| `init-characters.sh` | confirms `distill/persona.md` is the new source of truth | Apply phase rewrites this script to `cat distill/persona.md \| psql ...` |

---

## Drift detection

Before overwriting any `distill/*.md` file:

1. Read the current `distill/<file>.md`.
2. Run the new distillation in memory.
3. Diff old vs new. If non-empty diff, log it to `output/bundle-<ts>/eval-report.md` under a `## Drift detected` section so Yijun sees it.
4. Then write the new file.

This is the only way Yijun finds out he changed `update-prompts.sql` six weeks ago and forgot.

---

## What to do if Emma's repo structure shifts

If a key file moved (e.g. `backend/services/llm_service.py` → `backend/services/llm/service.py`), do **not** silently update the path in this file. Stop, write a `## Structural change detected` block in `eval-report.md`, and ask Yijun.

The skill assumes Emma's structure is stable. Structural shifts deserve human review because they affect the apply-phase patches.

---

## What this phase does NOT do

- Does not modify `prompts/`, `specs/`, or `plugins/`. Those are downstream of distillates and updated in Phase 2.
- Does not run any code. Everything is read-only file generation.
- Does not write to `output/` yet — that's Phase 2's job.

---

## Cache key

A run of Phase 1 is keyed on the SHA of Emma's `main` branch. If `git ls-remote` (or the GitHub web view) shows the same SHA as the previous run logged in `output/last-distill-sha`, skip all WebFetch — distillates are fresh.

```bash
EMMA_SHA=$(git ls-remote https://github.com/KrimsonSun/Emma_EmotionsAssistant main | cut -f1)
[ "$EMMA_SHA" = "$(cat output/last-distill-sha 2>/dev/null)" ] && echo "Cache hit, skipping distillation"
```

The `output/last-distill-sha` file is gitignored along with the rest of `output/`.
