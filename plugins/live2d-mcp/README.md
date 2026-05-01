# Live2D MCP plugin

Wraps Emma's existing Cubism 2.1 motion + expression assets as MCP tools the LLM can call directly. Closes the gap where empathic chat replies were not driving any visual reaction in the avatar.

## What it adds

| Tool | Effect |
|---|---|
| `play_motion(name, fade_ms?)` | Plays a `.mtn` motion on the avatar (head turn, body tap, head shake, etc.) |
| `set_expression(name, hold_ms?)` | Holds an expression file (`f01`–`f04`); auto-resets to `f01` after `hold_ms` |

Names come from filesystem scan at boot (`backend/models/live2d/emma/*.mtn` and `*.exp.json`) — never hardcoded, so adding a new motion file ships it as a tool option automatically.

## What it touches

| File | Action |
|---|---|
| `backend/mcp/plugins/live2d.py` | NEW — copied from `server-snippet.py` |
| `backend/api/routes/live2d_ws.py` | NEW — copied from `routes-snippet.py` |
| `backend/realtime.py` | NEW — copied from `realtime-snippet.py` (shared by future MCP plugins too) |
| `backend/main.py` | EDITED — `app.include_router(live2d_ws.router)` |
| `backend/mcp/server.py` | EDITED — register live2d plugin at boot |
| `frontend/src/components/Live2DViewer.jsx` | PATCHED — WS subscription + motion/expression dispatch + `data-current-motion` |

The `frontend/src/components/Live2DViewer.jsx` patch is shown as a unified diff during apply phase. Yijun reviews placement before merging — pixi-live2d-display init order matters.

## Pairing with persona

Examples 1, 2, 7 in `prompts/tool-call-examples.md` show the model pairing emotional cues with `play_motion` + `set_expression` calls. Without those few-shot examples, the LLM tends to ignore the new tools.

## Verifying it works

1. Apply phase succeeds, Emma rebuilds.
2. Open chat, type "我今天很难过".
3. In dev console: a network call to `/ws/live2d/<conversation_id>` is open.
4. After Emma replies: WS receives `{"event":"play_motion","name":"flickHead_00"}` (or `shake_00`).
5. Avatar visibly reacts.
6. `<canvas>` element has `data-current-motion` attribute updated.

The Playwright `live2d-mcp.spec.ts` test (Phase 3) automates these checks.

## Compatibility

- Existing REST `/context/{id}/tool-call` panel still works — both paths now exist.
- Cubism 4 backup model at `backend/models/live2d/emma_backup_20251202_230151/` is **not** touched. If you switch to Cubism 4 later, the motion name list rescan will need adjusting (`.mtn` → `.motion3.json`).
- WS connection is per-conversation. Switching conversations cleanly closes the previous WS.
