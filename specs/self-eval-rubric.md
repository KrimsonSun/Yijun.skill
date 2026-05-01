# Self-eval rubric

Defines what "successful" means for Emma's chat web. Two layers:

1. **Per-turn rubric** — the model emits a hidden JSON block after every reply. Cheap, real-time, self-rated.
2. **End-to-end rubric** — Playwright runs a 20-turn fixture and asserts aggregate scores. Authoritative.

The skill's iteration loop reads the end-to-end report and patches what failed.

---

## Per-turn rubric (model-emitted)

Every assistant reply ends with a fenced JSON block. The frontend strips it before rendering; the API returns it as a sibling field `rubric` (see `specs/tool-calling-protocol.md`).

```json
{
  "persona": 0.0,
  "length_ok": true,
  "markdown_clean": true,
  "tool_used_when_appropriate": true,
  "aesthetic_violation": null
}
```

### Field semantics

| Field | Type | Meaning | How model rates itself |
|---|---|---|---|
| `persona` | float 0–1 | Match to current persona's voice rules | Did I sound like Emma/Aria/Sage? Did I avoid wrong-persona vocabulary? |
| `length_ok` | bool | Reply ≤ 30 字 | Count chars in user-facing text only (excluding the JSON block) |
| `markdown_clean` | bool | No `**`, `##`, `-` bullets, ` ``` ` in user-facing text | Excludes the trailing JSON block (which is the only allowed fenced code) |
| `tool_used_when_appropriate` | bool | If user's input warranted a tool call (emotion → motion, game → action), did I call? Or true if no tool was warranted | Rate true if no tool was warranted; rate false if a clear cue went unhandled |
| `aesthetic_violation` | null \| string | Anything that breaks `distill/aesthetic.md` rules in this turn (e.g. linked an unstyled image) | null in 95%+ of turns |

### What model should NOT do

- Do not inflate `persona` self-score. The end-to-end rubric independently scores the same dimension and divergence > 0.2 between self-score and external-score is itself a flag.
- Do not omit the JSON block to "save tokens" — `rubric == null` is a hard fail.
- Do not put extra fields. Schema is closed.

---

## End-to-end rubric (Playwright fixture)

### Fixture: `eval/fixtures/20-turn-conversation.json`

A 20-turn scripted user side, mixing:
- 6 turns: pure emotional ("我今天好累", "开心，今天考试过了", "想哭")
- 5 turns: small-talk ("吃了吗", "周末干嘛", "有什么好剧推荐")
- 4 turns: game requests ("玩大富翁", "继续", "我掷", "结束")
- 3 turns: scale-trigger ("我已经一周没睡好了", "好像没什么意思", "都不想动")
- 2 turns: aesthetic probes ("帮我列个清单" — Emma should resist Markdown, give a single-line response)

### Dimensions and thresholds

| Dimension | Source | Threshold | What it measures |
|---|---|---|---|
| **Persona-self** | average of 20 `rubric.persona` | ≥ 0.85 | Model believes it stayed in character |
| **Persona-external** | grep on `reply` text for warmth markers vs. forbidden lexicon | ≥ 0.80 | Independent check; should match Persona-self ±0.2 |
| **Length compliance** | count `rubric.length_ok == true` | ≥ 18/20 | Hard ceiling on verbosity |
| **Markdown clean** | count `rubric.markdown_clean == true` | 20/20 | Zero tolerance |
| **Tool usage** | for the 6 emotional turns, ≥4 must trigger `play_motion` or `set_expression`. For the 4 game turns, all 4 must trigger a game tool. | ≥ 0.80 weighted | LLM is using the channel, not just narrating |
| **Aesthetic — colors** | sample bg of `.user-bubble` and `.assistant-bubble` after fixture replay; ΔE < 3 vs. token | pass/fail | Tokens not overridden |
| **Aesthetic — paw marquee** | `.paw-marquee` element exists with opacity 0.10–0.20 | pass/fail | Identity element |
| **Aesthetic — glass blur** | computed `backdrop-filter` on any `.panel` includes `blur(20px)` | pass/fail | |
| **Live2D triggered** | for the 6 emotional turns, canvas `data-current-motion` attribute changes value at least 4 times | ≥ 0.66 | The Live2D-MCP wiring actually fires |
| **Game — mount** | "玩大富翁" mounts panel within 2s | pass/fail | |
| **Game — turn loop** | within 4 game turns, `roll_dice` fires + `move_token` fires + `read_board` reflects new state | pass/fail | |
| **Self-eval JSON shape** | every API response includes valid `rubric` object | 20/20 | |

### Aggregate score

```
score = (persona_self + persona_external + length + markdown_clean
       + tool_usage + live2d_trigger) / 6

pass = score ≥ 0.80 AND every "pass/fail" dimension passed
```

The full report goes to `output/bundle-<ts>/eval-report.md` with each dimension's actual value, examples, and which turn(s) failed.

---

## Failure → patch routing

When a dimension fails, the iteration phase (Phase 5) edits the smallest unit:

| Failed dimension | Edit target |
|---|---|
| Persona-self / Persona-external | `distill/persona.md` voice rules (tighten or add forbidden lexicon entries) |
| Length compliance | `prompts/system-prompt.template.md` length reminder; possibly `prompts/tool-call-examples.md` few-shot showing tighter responses |
| Markdown clean | Add an explicit forbid line in persona rules + a few-shot showing the model resisting a "list me X" prompt |
| Tool usage low | `prompts/tool-call-examples.md` — add CN few-shot for the missed cue |
| Aesthetic colors | `distill/aesthetic.md` — re-check token values match `App.css`; rebuild bundle |
| Aesthetic paw / blur | Verify the apply phase didn't overwrite the marquee element; check `frontend-snippet.jsx` patches didn't strip classes |
| Live2D trigger | `plugins/live2d-mcp/server-snippet.py` motion name list; check WS broadcast actually reaches `Live2DViewer.jsx` |
| Game mount / loop | `plugins/<game>/manifest.json` trigger phrases + `mcp-tools.py` handler logic |
| Self-eval JSON shape | Strengthen the JSON-block instruction in `prompts/system-prompt.template.md`; add a hard example with the exact format |

---

## Why both layers

Per-turn rubric is fast feedback during development — Yijun can read 5 turns of `rubric` JSON in dev console and see Emma scoring herself. End-to-end rubric is what closes the iteration loop because it's:

1. **Reproducible** — same fixture, same prompts, same scores
2. **External** — doesn't trust the model's self-assessment for the visual/UI dimensions
3. **Scriptable** — `eval/run.sh` produces the report; iteration phase reads it

Don't trust either layer alone. The model can convince itself it's doing fine; Playwright can't catch tone subtleties.
