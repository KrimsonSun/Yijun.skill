# MCP plugin spec

Defines how a new MCP tool drops into Emma. The Live2D plugin in `plugins/live2d-mcp/` is the reference implementation; future MCP integrations (calendar, weather, music, photo memory) follow this shape.

This spec is the simpler sibling of `game-plugin-spec.md` — games extend this pattern with UI mounting, persistent state, and trigger phrases. Pure MCP tools don't need any of that.

---

## Plugin layout

```
plugins/<plugin-id>/
├── manifest.json              # tool list + metadata
├── server-snippet.py          # tool definitions (the registrar)
├── routes-snippet.py          # OPTIONAL — extra FastAPI routes (e.g. /ws/* channels)
├── frontend-snippet.jsx       # OPTIONAL — frontend wiring (e.g. Live2D motion subscriber)
└── README.md                  # what this MCP does, when LLM should call its tools
```

Apply phase copies / merges:
- `server-snippet.py` content → `backend/mcp/plugins/<plugin-id>.py` and import-registers from `backend/mcp/server.py` boot.
- `routes-snippet.py` → `backend/api/routes/<plugin-id>.py` and `include_router` in `backend/main.py`.
- `frontend-snippet.jsx` → either patches an existing component (Live2D's case) or lands at `frontend/src/components/<plugin-id>/`.

---

## `manifest.json`

```json
{
  "id": "live2d",
  "version": "0.1.0",
  "description": { "cn": "让大模型通过工具调用控制 Live2D 表情和动作", "en": "Let the LLM trigger Live2D motions/expressions" },
  "tools": [
    {
      "name": "play_motion",
      "description": "Play a named Live2D motion on Emma's avatar. Use to react emotionally to user.",
      "exposed_to_llm": true,
      "json_schema": {
        "type": "object",
        "properties": {
          "name": { "type": "string", "enum": ["idle_00","idle_01","idle_02","flickHead_00","flickHead_01","flickHead_02","pinchIn_00","pinchOut_00","shake_00","tapBody_00"] },
          "fade_ms": { "type": "integer", "default": 300 }
        },
        "required": ["name"]
      }
    },
    {
      "name": "set_expression",
      "description": "Hold a facial expression. f01=neutral, f02=happy, f03=sad, f04=surprised.",
      "exposed_to_llm": true,
      "json_schema": {
        "type": "object",
        "properties": {
          "name": { "type": "string", "enum": ["f01","f02","f03","f04"] },
          "hold_ms": { "type": "integer", "default": 2000 }
        },
        "required": ["name"]
      }
    }
  ],
  "ws_channels": ["/ws/live2d/{conversation_id}"],
  "frontend_patches": ["frontend/src/components/Live2DViewer.jsx"]
}
```

**Required:**
- `id`: kebab-case
- `version`: semver
- `tools[]`: each tool's name, description (LLM reads this verbatim — write it for the LLM, not for humans), `exposed_to_llm`, and `json_schema`

**Optional:**
- `ws_channels`: WebSocket paths the plugin opens. The skill scaffolds these in `routes-snippet.py`.
- `frontend_patches`: existing files this plugin needs to extend. The skill emits a unified diff Yijun reviews in apply phase.

---

## `server-snippet.py` shape

```python
from backend.mcp.server import MCPTool, MCPRegistry, ToolType, ToolError

def register(registry: MCPRegistry):
    registry.add(MCPTool(
        name="play_motion",
        description="Play a named Live2D motion on Emma's avatar. Use to react emotionally to user.",
        type=ToolType.FUNCTION,
        json_schema={...},  # mirrors manifest
        handler=_play_motion,
        exposed_to_llm=True,
        plugin_id="live2d",
    ))
    # ... set_expression

def _play_motion(conversation_id: str, args: dict) -> dict:
    name = args["name"]
    fade_ms = args.get("fade_ms", 300)
    # Validate name is in the actual filesystem listing — never trust LLM input alone
    if name not in _MOTION_NAMES:
        raise ToolError(f"Unknown motion: {name}")
    broadcast_ws(f"/ws/live2d/{conversation_id}", {
        "event": "play_motion",
        "name": name,
        "fade_ms": fade_ms,
    })
    return {"status": "queued", "name": name}
```

**Required:**
- A module-level `register(registry: MCPRegistry)` function. Called at FastAPI boot.
- Handlers take `(conversation_id: str, args: dict)` and return JSON-serializable.
- Validate inputs against the JSON schema **and** against runtime invariants (e.g. motion names exist on disk).

**WebSocket helper:**
- `broadcast_ws(channel, payload)` is added by Phase 2 in `backend/realtime.py`. Plugins call this to push events to subscribed frontend clients.

---

## `routes-snippet.py` (optional)

For plugins that need new HTTP/WS endpoints. Live2D needs `/ws/live2d/{conversation_id}`; a calendar plugin would need OAuth callback routes.

```python
from fastapi import APIRouter, WebSocket
from backend.realtime import register_channel

router = APIRouter(prefix="/ws/live2d")

@router.websocket("/{conversation_id}")
async def live2d_ws(websocket: WebSocket, conversation_id: str):
    await websocket.accept()
    await register_channel(f"/ws/live2d/{conversation_id}", websocket)
```

Apply phase wires `app.include_router(router)` into `backend/main.py`.

---

## `frontend-snippet.jsx` (optional)

For plugins that need to extend the chat UI's reaction layer. Live2D's snippet adds a `useEffect` to `Live2DViewer.jsx` that subscribes to the WS channel and dispatches motions to the existing pixi-live2d-display instance.

```jsx
// inside Live2DViewer.jsx, added by Live2D plugin patch
useEffect(() => {
  if (!conversationId || !modelRef.current) return;
  const ws = new WebSocket(`${WS_BASE}/ws/live2d/${conversationId}`);
  ws.onmessage = (msg) => {
    const evt = JSON.parse(msg.data);
    if (evt.event === "play_motion") {
      modelRef.current.motion(evt.name);
      canvasRef.current.dataset.currentMotion = evt.name;
    } else if (evt.event === "set_expression") {
      modelRef.current.expression(evt.name);
    }
  };
  return () => ws.close();
}, [conversationId]);
```

Apply phase emits this as a unified diff against the live `Live2DViewer.jsx` so Yijun reviews placement before the patch lands.

---

## Tool description writing rules

The `description` field is what the LLM uses to decide when to call. Write it for the LLM:

- Lead with the **action** ("Play a named Live2D motion"), not the noun ("Live2D motion player").
- State **when to use** in one clause ("Use to react emotionally to user.").
- If the tool has multiple modes, name them in the description so the LLM doesn't need to read the schema enum to discriminate.
- Don't describe the implementation. The LLM doesn't need to know about WebSockets.

Bad: `"This is a tool that uses pixi-live2d-display to control the Cubism 2.1 model's motion playback queue."`

Good: `"Play a named Live2D motion on Emma's avatar. Use to react emotionally to user — flickHead_00 for warmth, shake_00 for distress, tapBody_00 for excitement."`

---

## Lifecycle

1. **Install**: skill copies plugin folder → apply phase merges into Emma's tree → FastAPI boot calls plugin's `register()`.
2. **Discoverable**: tools appear in `MCPRegistry.list_tools_for_llm()` → LLM sees them.
3. **Invocable**: each chat turn, LLM may emit a tool call → dispatcher routes to handler → handler may broadcast WS events.
4. **Observable**: frontend subscribers (added via `frontend-snippet.jsx`) react to WS events.
5. **Removable**: skill's "uninstall" command (future) deletes the copied files and re-runs registry build.

---

## Reusing existing tools

Before authoring a new MCP plugin, check the existing `MCPRegistry`:

| Existing | What it does |
|---|---|
| `knowledge_base` | RAG over conversation history |
| `get_user_context` | Retrieve recent turns |
| `detect_emotion` | Sentiment classification |
| `generate_response` | Empathy reply (legacy — pre-tool-calling) |
| `get_psychological_scales` | List PHQ-9 / GAD-7 / etc. |
| `administer_scale` | Score user responses against a scale |

Don't duplicate. If your plugin needs sentiment, call `detect_emotion`. If it needs history, call `get_user_context`.

---

## Tests this spec must pass

- A new MCP plugin registered via `register()` shows up in `GET /mcp/tools` listing.
- The same plugin's tool appears in `MCPRegistry.list_tools_for_llm()` if `exposed_to_llm=True`.
- `live2d.spec.ts` Playwright test sends an empathic user message and asserts a `play_motion` tool call fires within 2s, plus `data-current-motion` attribute on canvas updates.
