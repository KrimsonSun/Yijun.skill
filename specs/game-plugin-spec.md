# Game plugin spec

Defines the shape every mini-game must take to drop into Emma. Yijun's 大富翁 is the reference implementation in `plugins/monopoly-game/`; future games (猜谜、抽卡、表情拼图、状态栏养成) follow the same pattern.

---

## Plugin layout

```
plugins/<game-id>/
├── manifest.json              # discovery + display + i18n
├── state.schema.json          # JSON Schema for the persisted game state
├── GamePanel.jsx              # mounted UI component (vanilla JSX, vanilla CSS)
├── game.css                   # per-component CSS, uses tokens from distill/aesthetic.md
├── mcp-tools.py               # tool definitions registered with MCPRegistry
└── system-prompt-fragment.md  # additions injected into Emma's system prompt when this game is "available"
```

The skill copies the entire folder into Emma at:
- `frontend/src/components/games/<game-id>/` for `GamePanel.jsx` + `game.css`
- `backend/games/<game-id>/` for `mcp-tools.py` + `state.schema.json`
- `frontend/src/games-manifest.json` is regenerated to list all installed games

---

## `manifest.json`

```json
{
  "id": "monopoly",
  "version": "0.1.0",
  "display_name": { "cn": "大富翁", "en": "Monopoly" },
  "description":  { "cn": "和 Emma 一起掷骰子，看谁先转一圈。", "en": "Roll dice with Emma." },
  "trigger_phrases": ["大富翁", "玩大富翁", "monopoly", "掷骰子"],
  "mount_component": "MonopolyPanel",
  "mcp_tools": ["roll_dice", "move_token", "read_board", "end_turn"],
  "state_path": "/games/monopoly/state",
  "min_players": 2,
  "max_players": 2,
  "live2d_reactions": {
    "win":  { "motion": "tapBody_00",   "expression": "f02" },
    "lose": { "motion": "shake_00",     "expression": "f03" },
    "roll": { "motion": "flickHead_00" }
  }
}
```

**Required fields:**
- `id`: kebab-case, used for routing (`/games/<id>/...`).
- `version`: semver. The skill records this in the bundle's `eval-report.md`.
- `display_name`: bilingual; consumed by `i18n.js`.
- `trigger_phrases`: substrings the LLM watches in user input. The system-prompt template injects these so the model knows when to mount.
- `mount_component`: the named React export from `GamePanel.jsx`.
- `mcp_tools`: tool names this game registers. They appear in the LLM's tool list **only when the game is mounted** (or always — see "Tool visibility" below).
- `state_path`: REST path the panel polls/PUTs to read/write state. Backend persists per-conversation.

**Optional:**
- `live2d_reactions`: maps game events to Live2D motions/expressions. The skill auto-wires these so when the game emits a `win` event, Emma's avatar plays `tapBody_00` + sets expression `f02`.

---

## `state.schema.json`

JSON Schema the game's state must validate against. Backend uses this for `/games/<id>/state` GET/PUT validation; frontend uses it for type hints.

Example (Monopoly):

```json
{
  "$schema": "http://json-schema.org/draft-07/schema#",
  "type": "object",
  "required": ["board", "players", "turn", "started_at"],
  "properties": {
    "board": {
      "type": "array",
      "items": { "type": "object", "properties": { "name": {"type": "string"}, "owner": {"type": ["string", "null"]} } }
    },
    "players": {
      "type": "array",
      "items": { "type": "object", "properties": { "id": {"type": "string"}, "position": {"type": "integer"}, "money": {"type": "integer"} } }
    },
    "turn": { "type": "string", "enum": ["user", "emma"] },
    "started_at": { "type": "string", "format": "date-time" }
  }
}
```

---

## `GamePanel.jsx` contract

```jsx
// Named export must match manifest.mount_component
export function MonopolyPanel({ conversationId, onClose }) {
  // 1. Read state from `/games/monopoly/state?conversation_id=...`
  // 2. Render board / players / dice using vanilla CSS classes from game.css
  // 3. Subscribe to a WS channel `/ws/games/monopoly/{conversation_id}` for state updates
  //    pushed by MCP tool calls (so when Emma rolls, user sees update without polling)
  // 4. Provide user-action buttons that POST to /context/{conversation_id}/tool-call
  //    so user actions reuse the same dispatcher
}
```

**Constraints:**
- No new state library. Use `useState` / `useReducer` / `useContext`.
- Read CSS variables from `App.css`. Don't hardcode colors. Specifically use `--primary-color`, `--glass-bg`, `--panel-shadow`.
- Mount into a slot the skill adds to `App.jsx`: `<GameSlot mountedGame={mountedGame} />`. The slot uses `fadeInUp 0.3s` for entrance.
- Unmount when `onClose()` is called (X button or chat says "结束游戏").

---

## `game.css` constraints

```css
.monopoly-panel {
  background: var(--glass-bg);
  backdrop-filter: blur(20px);
  border-radius: 16px;
  box-shadow: var(--panel-shadow);
  padding: 16px;
  animation: fadeInUp 0.3s ease-out;
}

.monopoly-tile {
  border: 1px solid var(--glass-border);
  background: var(--assistant-bg);
  /* ... */
}

.monopoly-button-primary {
  background: var(--primary-color);
  color: white;
  border-radius: 12px;
  /* never use other primary colors */
}
```

Lint (manual or via the rubric): every game.css uses **only** the tokens from `distill/aesthetic.md`. No hex literals except inside `--primary-*` derivative comments.

---

## `mcp-tools.py` shape

```python
from backend.mcp.server import MCPTool, MCPRegistry, ToolType

def register(registry: MCPRegistry):
    registry.add(MCPTool(
        name="roll_dice",
        description="Roll two six-sided dice for the current player. Returns {'dice': [int, int], 'sum': int}.",
        type=ToolType.FUNCTION,
        json_schema={"type": "object", "properties": {}, "required": []},
        handler=_roll_dice,
        exposed_to_llm=True,
        plugin_id="monopoly",
    ))
    # ... move_token, read_board, end_turn

def _roll_dice(conversation_id: str, args: dict) -> dict:
    state = load_state(conversation_id)
    if state["turn"] != "emma":
        raise ToolError("Not Emma's turn")
    a, b = randint(1, 6), randint(1, 6)
    state["last_roll"] = [a, b]
    save_state(conversation_id, state)
    broadcast_ws(f"/ws/games/monopoly/{conversation_id}", {"event": "roll", "dice": [a, b]})
    fire_live2d_reaction("monopoly", "roll", conversation_id)
    return {"dice": [a, b], "sum": a + b}
```

**Required handler signature:** `(conversation_id: str, args: dict) -> dict | str | int`.

`fire_live2d_reaction(plugin_id, event, conversation_id)` is a helper added in Phase 2 — reads `manifest.live2d_reactions` and pushes a Live2D WS event. This is how games trigger Emma's avatar without each game knowing about Live2D internals.

---

## `system-prompt-fragment.md`

Markdown injected into the system prompt under `## Available games` when this plugin is installed:

```markdown
### 大富翁 (monopoly)
当用户提到「{trigger_phrases}」时，调用 mount_game("monopoly") 启动。
轮到你时调用 roll_dice() → move_token() → end_turn()。
胜利会触发 tapBody 动作，输了会触发 shake。
保持 Emma 的语气：紧张时就「啊我抖了！」，赢了「贴贴~ 我赢啦💕」。
```

The skill renders these fragments in alphabetical order by `id` and concatenates them into the final system prompt's `{available_games}` placeholder.

---

## Tool visibility

Two modes (set per-tool via `exposed_to_llm`):

1. **Always exposed** (default): Tool appears in LLM's tool list every chat turn. Used for tools that double as triggers (`mount_game`, `roll_dice` if you want it callable even before mounting).
2. **Mount-gated**: Tool appears only after the game is mounted. The `MCPRegistry.list_tools_for_llm()` filters by active plugin set per conversation.

For Monopoly: `mount_game` is always exposed; `roll_dice`, `move_token`, `end_turn` are mount-gated.

---

## Plugin lifecycle

1. **Discovery**: skill copies plugin folder into Emma → `register()` is called at FastAPI startup → `MCPRegistry` knows about the tools.
2. **User mention**: LLM sees `trigger_phrases` in user input → calls `mount_game(id)`.
3. **Mount**: `mount_game` writes initial state via `state.schema.json` defaults → broadcasts WS event to frontend → `App.jsx` mounts the panel.
4. **Play**: turns alternate; each tool call mutates state, broadcasts updates, and (optionally) fires Live2D reactions.
5. **Unmount**: user says "结束游戏" or wins/loses → `end_game(id)` called → state archived → frontend unmounts panel.

---

## Reference implementation

See `plugins/monopoly-game/` once Phase 3 lands. Read it as the canonical example before authoring a new game plugin.

---

## Forbidden in game plugins

- ❌ Adding a new state library (must use React Context + `useReducer`)
- ❌ Hardcoded colors (must use CSS variables from `distill/aesthetic.md`)
- ❌ A game that requires markdown in the chat reply (Emma's voice constraint trumps gameplay narration)
- ❌ Heavy assets (>500KB per file) without compression
- ❌ Real-money gameplay, gambling mechanics, or anything that conflicts with Emma's emotional-companion role
