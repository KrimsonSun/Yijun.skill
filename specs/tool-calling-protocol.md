# Tool-calling protocol

Defines how the LLM in Emma's chat path invokes MCP tools. **This is the gap the skill closes.** Currently, `backend/services/llm_service.py` calls the LLM with plain text in/out and the MCP server is only reachable via REST from `MCPPanel.jsx`. After applying the skill's patches, MCP tools become first-class to the LLM.

---

## Goals

1. Reuse the existing MCP dispatcher at `backend/api/routes/mcp.py` (REST `/context/{id}/tool-call`). Don't fork the dispatch path.
2. Keep the chat reply contract unchanged for the frontend (`ChatPanel.jsx` doesn't need to know tools were called).
3. Expose every registered MCP tool to the LLM via the unified function-calling shape OpenAI and Gemini both accept.
4. Allow plugins (Live2D, Monopoly) to register their tools through the same `MCPRegistry` Emma already uses.

---

## Architecture

```
ChatPanel.jsx  →  POST /api/chat  →  routes/chat.py
                                       │
                                       ▼
                              llm_service.generate_response(
                                  user_msg,
                                  history,
                                  persona_prompt,
                                  tool_registry,    ← NEW
                                  conversation_id   ← NEW (for tool side-effects)
                              )
                                       │
                                       ▼
              ┌──── LLM (OpenAI / Gemini) with function-calling enabled
              │             │
              │             │ tool_calls?
              │             ▼
              │     for tool_call in tool_calls:
              │         POST /context/{conversation_id}/tool-call
              │         (reuses existing MCP REST dispatcher)
              │             │
              │             ▼
              │     append tool result to message history
              │             │
              └─────────────┘ (loop until LLM returns plain content)
                            │
                            ▼
                  reply_text + self_eval_json
                            │
                            ▼
                  return to ChatPanel.jsx (rubric JSON stripped on render)
```

---

## Patch points

### `backend/mcp/server.py`

Add to `MCPRegistry`:

```python
def list_tools_for_llm(self) -> list[dict]:
    """Return tools in OpenAI/Gemini function-calling format."""
    return [
        {
            "type": "function",
            "function": {
                "name": tool.name,
                "description": tool.description,
                "parameters": tool.json_schema,  # already a dict per existing dataclass
            },
        }
        for tool in self.tools.values()
        if tool.exposed_to_llm  # NEW field — defaults True for new tools
    ]
```

Add `exposed_to_llm: bool = True` to the existing `MCPTool` dataclass. Existing tools (`knowledge_base`, etc.) keep default `True`. Tools that should stay panel-only (e.g. an admin debug tool added later) can set `False`.

### `backend/services/llm_service.py`

Replace the current single-shot `generate_response` with a tool-loop:

```python
async def generate_response(
    user_msg: str,
    history: list[dict],
    persona_prompt: str,
    tool_registry: MCPRegistry,
    conversation_id: str,
) -> tuple[str, dict]:
    messages = [{"role": "system", "content": persona_prompt}, *history,
                {"role": "user", "content": user_msg}]
    tools = tool_registry.list_tools_for_llm()

    for _ in range(MAX_TOOL_ITERS):  # MAX_TOOL_ITERS = 5
        resp = await llm_client.chat(messages=messages, tools=tools)
        if not resp.tool_calls:
            reply_text, self_eval = split_reply_and_eval(resp.content)
            return reply_text, self_eval
        for tc in resp.tool_calls:
            result = await mcp_dispatch(conversation_id, tc.name, tc.arguments)
            messages.append({"role": "assistant", "tool_calls": [tc.dict()]})
            messages.append({"role": "tool", "tool_call_id": tc.id, "content": str(result)})

    raise ToolLoopTimeout("LLM did not converge to a final reply within 5 iterations")
```

`mcp_dispatch` is a thin internal call that hits the existing handler in `routes/mcp.py` (or, more efficiently, calls `MCPRegistry.invoke()` directly to skip the HTTP roundtrip in-process).

`split_reply_and_eval` parses the trailing fenced JSON block (see `distill/persona.md`) and returns the user-facing text + the rubric dict. If no JSON block found, the rubric is filled with `{"persona": null, "length_ok": null, ...}` and the eval marks it as a self-eval failure.

### `backend/api/routes/chat.py`

Change the call site:

```python
@router.post("/chat")
async def chat(payload: ChatRequest, db: Session = Depends(get_db)):
    persona_prompt = load_persona(payload.character_id)
    history = load_history(db, payload.conversation_id)
    registry = mcp_registry  # module-level singleton

    reply, rubric = await llm_service.generate_response(
        payload.message, history, persona_prompt,
        registry, payload.conversation_id,
    )

    persist_turn(db, payload.conversation_id, payload.message, reply, rubric)
    return {"reply": reply, "rubric": rubric}
```

The `rubric` dict is returned alongside `reply` so the Playwright eval can read it without parsing the reply text. Frontend `ChatPanel.jsx` only renders `reply` — it ignores `rubric`.

---

## Compatibility — keeping the panel path alive

`MCPPanel.jsx` continues to work because the tool-calling protocol **does not** remove the REST `/context/{id}/tool-call` endpoint. Both paths now exist:

- LLM-driven: model emits a tool_call, server dispatches via `MCPRegistry.invoke()` directly.
- Panel-driven: user clicks a button, frontend POSTs to `/context/{id}/tool-call`, same handler runs.

This is intentional. Yijun uses the panel for debugging; the LLM path is the user-facing automation.

---

## Tool-call cadence — when the LLM should call vs. just reply

Embedded into the system prompt (see `prompts/system-prompt.template.md`):

```
- 用户表达情绪（开心/难过/累/焦虑）→ play_motion 或 set_expression（Live2D 反应）
- 用户提到「玩 X 游戏」→ 启动游戏（mount_game(id) 或具体游戏的初始化工具）
- 游戏中轮到 Emma 行动 → 调用游戏的 action 工具（roll_dice, move_token, ...）
- 用户描述心情且持续多轮负面 → administer_scale("PHQ-9") 提议（不强推）
- 单纯闲聊 / 安慰 → 不调用工具，直接回复
```

The model must **never** describe the tool call in user-facing text. Tool calls happen in the tool-call channel; the reply is the natural-language continuation.

---

## Failure modes

| Failure | Symptom | Fix |
|---|---|---|
| `MAX_TOOL_ITERS` exceeded | Reply absent, log shows tool-loop timeout | Inspect the last tool result — model is probably stuck retrying a failing tool. Check `MCPRegistry.invoke` error path. |
| LLM emits markdown in reply | Frontend strips `**` but headings persist | Tighten persona prompt; rubric `markdown_clean: false` should already flag |
| Tool call with unknown name | Server returns 404 from dispatcher | Add tool to `MCPRegistry`; ensure plugin registered before chat boot |
| Self-eval JSON missing | `rubric.persona == null` | Few-shot in `prompts/tool-call-examples.md` shows the format; reinforce |
| Tool fired but UI didn't update (Live2D) | Motion attr unchanged on canvas | WS channel `/ws/live2d/{conversation_id}` not connected; check `Live2DViewer.jsx` `useEffect` deps |

---

## Tests this protocol must pass (Playwright)

- `live2d-mcp.spec.ts`: send "我今天很难过", assert a `play_motion` tool call appears in network log within 2s, and `data-current-motion` attr changes.
- `monopoly.spec.ts`: send "我们玩大富翁吧", assert game panel mounts, assert `roll_dice` tool fires when prompted.
- `self-eval.spec.ts`: across 20 turns, assert every response includes `rubric` with valid shape and average score ≥ 0.8 per dimension.
