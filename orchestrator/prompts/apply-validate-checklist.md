# Apply gate — validation checklist

You're about to land an iteration into Emma on a fresh `yijun-skill/<run>/iter-N` branch. Before you say `y`, scan the diff for these things. Two minutes of review here saves you a forced revert later.

## Stack discipline (red flags — say `n` if you see any)

- [ ] **No `.tsx` files**, no `tsconfig.json`, no `@types/*` runtime deps
- [ ] **No Tailwind / styled-components / emotion / Material-UI** classes or imports
- [ ] **No Next.js** files (`app/`, `pages/`, `next.config.*`)
- [ ] **No official `mcp` Python SDK** import (`from mcp import ...`)
- [ ] **No `asyncpg`**, no swap of `psycopg2` for anything else
- [ ] **No new state library** (`zustand`, `redux`, `jotai`, …)

If any of these appear, the orchestrator drifted. Decline and inspect `distill/stack.md` — the rules there are explicit about what's forbidden.

## Persona / aesthetic discipline

- [ ] System prompt at `backend/persona/system-prompt.md` still contains the `≤30字` rule and the "彻底忘掉你是AI助手" line
- [ ] No new color literals — game CSS uses `var(--primary-color)` / `var(--glass-bg)` / `var(--panel-shadow)`
- [ ] Live2D motion names in `backend/mcp/plugins/live2d.py` match the actual `.mtn` files in `backend/models/live2d/emma/` (no fabricated names like `wave_00`)

## Wiring sanity

- [ ] `backend/realtime.py` was added (or already exists) — required by Live2D and game plugins
- [ ] Each `backend/api/routes/*_orch.py` has a corresponding `app.include_router` line that **the orchestrator did NOT touch yet** (`main.py` edits are intentionally manual; orchestrator drops the route file but doesn't auto-register it)
- [ ] `_pending/` folder has frontend snippets you'll need to paste into `Live2DViewer.jsx` manually — orchestrator never auto-edits that file because pixi init order matters

## Test surface

- [ ] `eval/tests/*.spec.ts` and `eval/fixtures/*.json` landed under Emma's `eval/`
- [ ] Persona fixture includes the 20-turn mix; if it's been replaced with anything shorter, decline (rubric thresholds assume 20 turns)

## After saying `y` — manual follow-up steps

These are intentionally **not** automated because they need eyes:

1. **Wire the route**: in `backend/main.py`, add for each new `*_orch.py`:
   ```python
   from backend.api.routes import live2d_orch, monopoly_orch
   app.include_router(live2d_orch.router)
   app.include_router(monopoly_orch.router)
   ```

2. **Wire the MCP plugin**: in `backend/mcp/server.py` boot:
   ```python
   from backend.mcp.plugins import live2d
   from backend.games.monopoly import tools as monopoly_tools
   live2d.register(registry)
   monopoly_tools.register(registry)
   ```

3. **Merge `Live2DViewer.jsx` snippet** from `backend/persona/_pending/live2d-frontend-snippet.jsx` into the actual component. The snippet is a unified diff — don't paste blindly; check that `modelRef` and `canvasRef` names match the existing component.

4. **Mount the game**: in `App.jsx`, add `<GameSlot mountedGame={mountedGame} />` between `<ChatPanel>` and `<Live2DViewer>` if not already there. The `mountedGame` state is set by the `mount_game` MCP tool result.

After all four are done, the eval phase will have something to actually test. Skipping any of them = automatic eval failure.

## If anything looks wrong but the diff is "mostly OK"

Don't hand-edit on the iter branch — the orchestrator will think the next iteration cleanly inherits from `origin/main` and silently overwrite your edits. Instead:

1. Decline (`n`)
2. Edit the offending file in `Yijun.skill/` (e.g. `prompts/tool-call-examples.md` or `plugins/<id>/...`)
3. Commit in `Yijun.skill`
4. Re-run `iterate.sh` — the next iter will pick up your fix
