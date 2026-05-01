# Monopoly game plugin (大富翁)

Reference implementation of the [game-plugin-spec](../../specs/game-plugin-spec.md). Yijun mentioned the logic was mostly done locally — this plugin gives a clean slate that follows Emma's persona and aesthetic, ready to merge or replace with his existing version.

## What it adds

| Tool | Effect |
|---|---|
| `mount_game(id="monopoly")` | Initializes a 12-tile board, two players (you / Emma), $1500 each |
| `roll_dice()` | Two 6-sided dice for current player; fires Live2D `flickHead_00` |
| `move_token(player_id?, steps?)` | Moves token by `steps` or `last_roll` sum; passing-go bonus $200 |
| `read_board()` | Returns full state — board, players, turn, last roll |
| `end_turn()` | Hands turn to other player |
| `end_game()` | Closes the session |

Win condition: first player to lap the board wins. Auto-fires Live2D `tapBody_00` + expression `f02` (Emma wins) or `shake_00` + `f03` (Emma loses).

## What it touches

| File | Action |
|---|---|
| `backend/games/monopoly/tools.py` | NEW — copied from `mcp-tools.py` |
| `backend/games/monopoly/manifest.json` | NEW — copied from `manifest.json` |
| `backend/api/routes/monopoly.py` | NEW — copied from `routes-snippet.py` |
| `backend/main.py` | EDITED — `app.include_router(monopoly.router)` |
| `backend/mcp/server.py` | EDITED — register monopoly tools at boot |
| `frontend/src/components/games/MonopolyPanel.jsx` | NEW — copied from `GamePanel.jsx` |
| `frontend/src/styles/monopoly.css` | NEW — copied from `game.css` |
| `frontend/src/App.jsx` | PATCHED — adds `<GameSlot>` between `<ChatPanel>` and `<Live2DViewer>`; mounts `MonopolyPanel` when `mountedGame === 'monopoly'` |

`mountedGame` state lives in App.jsx context, set by `mount_game` tool result via the same WS channel pattern.

## Pairing with persona

`system-prompt-fragment.md` injects rules so Emma:
- Reacts in-character to dice / win / loss
- Doesn't narrate the board (UI shows it)
- Stays under 30 字 even mid-game

Without this fragment, the LLM tends to drift into commentator mode and break the persona length rule.

## State persistence

In-memory dict keyed by `conversation_id` (see `_STATE_BY_CONV` in `mcp-tools.py`). Survives chat reloads if the FastAPI process didn't restart.

If Yijun wants persistence across restarts, swap `_STATE_BY_CONV` for a Postgres `monopoly_state` table — handlers don't need other changes.

## Replacing with Yijun's existing implementation

If Yijun has a more featureful 大富翁 locally:
1. Keep `manifest.json` (the skill needs it for plugin discovery + Live2D reactions).
2. Replace `mcp-tools.py` with his handler logic, but keep the `register()` function shape.
3. Replace `GamePanel.jsx` with his UI, but keep the `MonopolyPanel` named export and the WS subscription pattern.
4. Re-run skill emit phase — eval will catch persona/aesthetic drift if he reused other tokens.

## Verifying it works

1. Apply phase succeeds, Emma rebuilds.
2. Type "我们玩大富翁吧". Emma replies short + warm; `<MonopolyPanel>` mounts within 2s.
3. Type "到你了". Network log shows `roll_dice` → `move_token` → `end_turn` tool calls. Live2D fires `flickHead_00`. Token moves on the board.
4. Loop. After ~12 turns total someone laps the board, win/lose Live2D reaction fires, panel shows endgame state.

The Playwright `monopoly.spec.ts` test automates these checks.
