# Yijun.skill

A Claude Code skill that distills Yijun's personal agent style from his GitHub (anchored on [Emma_EmotionsAssistant](https://github.com/KrimsonSun/Emma_EmotionsAssistant)) and emits a **prompt suite + Playwright eval bundle** that Emma's React/Vite chat absorbs.

The skill is a meta-tool: each invocation re-reads Emma's current state, regenerates persona/aesthetic/stack distillates, and emits a versioned bundle of patches and tests that drop into Emma. It also runs the eval and iterates the prompt until the rubric passes.

## When to use

- 重新蒸馏人格/审美 — pull the latest persona prompts and CSS tokens from Emma's GitHub
- 让 chat 通过 MCP 触发 Live2D — wire LLM tool-calling so empathy responses fire `play_motion` / `set_expression`
- 加新小游戏 — drop a plugin into Emma's pluggable game shape (大富翁 ships as the reference)
- 评估这个网页是否成功 — run Playwright with rubric scoring across a 20-turn fixture

## Repo layout

| Folder | What it is |
|---|---|
| `SKILL.md` | Entrypoint Claude reads when the skill is invoked. Defines the 5-phase workflow. |
| `distill/` | Source-of-truth derived from Emma's GitHub. Re-generated each Phase 1. |
| `specs/` | Contracts the emitted bundle must satisfy (tool-calling, plugins, rubric). |
| `prompts/` | System prompt template + persona snippets + CN few-shot. |
| `plugins/` | Ready-to-drop integrations. `live2d-mcp` (Phase 2) and `monopoly-game` (Phase 3). |
| `eval/` | Playwright config + tests + `run.sh`. |
| `output/` | Gitignored. Each invocation drops a `bundle-<timestamp>/` here. |

## Workflow (per invocation)

1. **Distill** — re-read Emma GH; regenerate `distill/persona.md` / `aesthetic.md` / `stack.md`.
2. **Emit** — render `prompts/system-prompt.template.md` + copy plugins → `output/bundle-<ts>/`.
3. **Apply** — show diff against local Emma checkout; user approves; patches land.
4. **Eval** — `eval/run.sh` boots Emma docker-compose + runs Playwright + writes `eval-report.md`.
5. **Iterate** — read failures, edit smallest unit, loop.

See [SKILL.md](SKILL.md) for the full workflow.

## Status

- ✅ Phase 1 (Distill + specs + prompts) — complete
- 🚧 Phase 2 (Live2D MCP plugin + tool-calling patch) — pending
- 🚧 Phase 3 (Monopoly plugin + Playwright eval + iteration loop) — pending

## How to invoke

From Claude Code in the `Yijun.skill` repo:

```
/yijun-distill
```

(Or any phrase that matches the SKILL.md trigger conditions: "蒸馏 agent", "迭代 Emma", "加新游戏到 Emma", "Live2D MCP", "评估聊天网页".)

## Related repos

- [Emma_EmotionsAssistant](https://github.com/KrimsonSun/Emma_EmotionsAssistant) — the chat web this skill iterates
- [AutoArxivSummarization](https://github.com/KrimsonSun/AutoArxivSummarization) — Yijun's other Next.js project (different stack; **not** the aesthetic baseline for this skill)
