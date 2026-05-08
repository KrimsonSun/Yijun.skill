---
name: yijun-distill
description: Distill Yijun's personal agent style from his GitHub (anchored on Emma_EmotionsAssistant) and emit a prompt suite + Playwright eval bundle that Emma's React/Vite chat absorbs. Use when the user wants to (a) refresh Emma's persona/aesthetic from latest GH state, (b) wire LLM tool-calling into chat so MCP tools (Live2D, mini-games) actually fire from the model, (c) add a new mini-game or MCP tool that follows Emma's existing conventions, or (d) self-evaluate whether the chat web is "successful" via Playwright. Trigger on phrases like "蒸馏 agent", "迭代 Emma", "加新游戏到 Emma", "Live2D MCP", "评估聊天网页". Do NOT trigger for unrelated React/Next.js work in other repos.
---

# yijun-distill

This skill keeps Yijun's web chat (`Emma_EmotionsAssistant`) coherent with his personal agent identity as it grows. It reads source-of-truth signals from his GitHub, writes them into versioned distillates here, and emits a bundle Emma's frontend/backend can absorb. Each invocation is one **iteration**: distill → emit → apply → eval → patch.

## When to invoke

Run this skill when the user asks to:
- 重新蒸馏人格/审美 (re-extract persona or aesthetic from latest Emma state)
- 让 chat 通过 MCP 触发 Live2D / 调用工具 (wire LLM tool-calling)
- 加一个新小游戏 / 新 MCP (drop a plugin into Emma's pluggable shape)
- 评估这个网页是否成功 (run Playwright self-evaluation with rubric scoring)

Do **not** invoke for unrelated React work, generic prompt engineering, or repos other than `Emma_EmotionsAssistant`.

## Repo layout (this skill)

```
Yijun.skill/
├── SKILL.md                          # this file — workflow + invocation rules
├── README.md                         # human-facing overview
├── distill/                          # source-of-truth derived from Emma GH state
│   ├── persona.md                    # Emma + Aria + Sage personas (CN canonical)
│   ├── aesthetic.md                  # CSS tokens, motion, breakpoints
│   ├── stack.md                      # React+Vite+JSX, FastAPI, custom MCP
│   └── extract.md                    # re-distillation playbook
├── specs/                            # contracts the bundle must satisfy
│   ├── tool-calling-protocol.md      # chat.py ↔ LLM ↔ MCP wiring contract
│   ├── game-plugin-spec.md           # mini-game plugin shape
│   ├── mcp-plugin-spec.md            # new MCP tool registration shape
│   └── self-eval-rubric.md           # JSON rubric the model emits per turn
├── prompts/                          # rendered into Emma's runtime
│   ├── system-prompt.template.md     # parameterized
│   ├── persona-snippets/             # ready-to-inject persona blocks
│   └── tool-call-examples.md         # CN few-shot for tool-use
├── plugins/                          # ready-to-drop integrations
│   ├── live2d-mcp/                   # wraps Cubism 2.1 motions/expressions as MCP tools
│   └── monopoly-game/                # reference 大富翁 plugin
├── eval/                             # Playwright + rubric harness
│   ├── playwright.config.ts
│   ├── tests/
│   ├── fixtures/
│   └── run.sh
└── output/                           # gitignored — generated bundles
    └── bundle-<timestamp>/
```

## Workflow — five phases per invocation

Claude follows these phases in order. Skip a phase only if the user explicitly says so.

### Phase 1 — Distill

Re-read Emma's GitHub state and regenerate `distill/`. Idempotent: same GH state → same files. Catches drift if Yijun edited persona SQL or CSS tokens since last run.

**Sources to read** (in order):
1. `https://github.com/KrimsonSun/Emma_EmotionsAssistant/blob/main/update-prompts.sql` — persona prompts for Emma/Aria/Sage
2. `https://github.com/KrimsonSun/Emma_EmotionsAssistant/blob/main/backend/services/llm_service.py` — hardcoded directive about being a "现实人类伴侣"
3. `https://github.com/KrimsonSun/Emma_EmotionsAssistant/blob/main/frontend/src/App.css` — CSS variables (Glassmorphic Pink)
4. `https://github.com/KrimsonSun/Emma_EmotionsAssistant/blob/main/frontend/package.json` — pinned deps (don't drift)
5. `https://github.com/KrimsonSun/Emma_EmotionsAssistant/blob/main/backend/mcp/server.py` — current MCP tool list
6. `https://github.com/KrimsonSun/Emma_EmotionsAssistant/tree/main/backend/models/live2d/emma` — motion/expression file lists

**Actions:**
- Update `distill/persona.md` with verbatim CN persona blocks for each character + voice rules.
- Update `distill/aesthetic.md` with current CSS variable values, motion timings, breakpoints, paw-print rule.
- Update `distill/stack.md` with current pinned versions and forbidden-substitution list (no TS, no Tailwind, no Next.js, no official `mcp` SDK).
- Diff against previous distillates; if anything changed, log it in the bundle's `eval-report.md` so Yijun knows.

### Phase 2 — Emit

Render the bundle into `output/bundle-<timestamp>/`. Nothing touches Emma yet.

**Outputs:**
- `system-prompt.md` — `prompts/system-prompt.template.md` with `{persona}`, `{available_tools}`, `{available_games}`, `{rubric}` substituted.
- `chat.py.patch` and `llm_service.py.patch` — implement `specs/tool-calling-protocol.md`.
- `live2d-mcp/` — copy from `plugins/live2d-mcp/`.
- `monopoly-game/` — copy from `plugins/monopoly-game/` if user asked for it.
- `playwright/` — copy `eval/tests/` + `playwright.config.ts`.

### Phase 3 — Apply

Ask the user once for their local `Emma_EmotionsAssistant` checkout path; cache in `~/.yijun-skill/emma-path`. Show a unified diff of every file the bundle would touch. **Do not write** until user approves.

Files the apply phase modifies in Emma:
- `backend/services/llm_service.py` — add tool-calling loop
- `backend/api/routes/chat.py` — pass tool registry to LLM service
- `backend/mcp/server.py` — register new tools, expose `list_tools_for_llm()`
- `backend/api/routes/live2d.py` — add `/ws/live2d/{conversation_id}`
- `frontend/src/components/Live2DViewer.jsx` — subscribe to WS, dispatch motion/expression
- `frontend/src/components/ChatPanel.jsx` — strip rubric JSON from rendered text
- `init-characters.sh` — read persona from skill's `distill/persona.md` instead of inline
- (only if Monopoly chosen) `frontend/src/components/games/MonopolyPanel.jsx`, `frontend/src/styles/monopoly.css`, `backend/games/monopoly.py`

**Do not edit** `update-prompts.sql` directly — persona is now sourced from `distill/persona.md`.

### Phase 4 — Eval

Run `eval/run.sh`. Steps:
1. `cd $EMMA_PATH && docker-compose up -d` (skip if already up)
2. `cd $SKILL_PATH/eval && npx playwright test`
3. Collect per-turn rubric JSON the model emitted (Playwright fixture replays a 20-turn conversation)
4. Write `output/bundle-<ts>/eval-report.md` with pass/fail per dimension and aggregate scores

### Phase 5 — Iterate

Read `eval-report.md`. For each failed dimension, edit the smallest unit:
- Persona fail → edit `distill/persona.md` voice rules
- Tool-call fail → edit `prompts/tool-call-examples.md` few-shot or `specs/tool-calling-protocol.md`
- Aesthetic fail → check `distill/aesthetic.md` matches current `App.css`; rebuild bundle
- Live2D fail → check `plugins/live2d-mcp/server-snippet.py` motion name list against `backend/models/live2d/emma/`
- Monopoly fail → debug `plugins/monopoly-game/`

Loop Phase 2 → 4 until all dimensions ≥ threshold or user calls stop.

## Invocation rules

- **Always start with Phase 1.** Don't trust cached `distill/` files across sessions; Emma may have changed.
- **Never edit Emma directly without showing a diff first.** Apply phase requires explicit user approval.
- **Never introduce TypeScript, Tailwind, Next.js, or the official `mcp` SDK** into Emma. See `distill/stack.md` for the forbidden list.
- **Persona is CN-canonical.** Don't translate persona prompts to EN unless user asks. Skill spec docs (this file, `specs/*.md`) stay in EN — they're for Claude/devs.
- **Live2D motion names come from the filesystem**, not from imagination. Always re-read `backend/models/live2d/emma/` listing in Phase 1 before exposing motion tools.
- **Eval thresholds:** every dimension in `specs/self-eval-rubric.md` must average ≥ 0.8 across the 20-turn fixture before declaring success.

## Reading the rest of the skill

- Persona / voice details → `distill/persona.md`
- Pink-glass aesthetic tokens → `distill/aesthetic.md`
- Stack rules and forbidden substitutions → `distill/stack.md`
- How tool-calling is wired into Emma's existing chat → `specs/tool-calling-protocol.md`
- How a new mini-game plugs in → `specs/game-plugin-spec.md`
- How a new MCP tool registers → `specs/mcp-plugin-spec.md`
- What "successful" means concretely → `specs/self-eval-rubric.md`
