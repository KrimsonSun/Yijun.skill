# Eval — Playwright + rubric harness

Runs the 20-turn fixture against a local Emma instance, scores each dimension defined in [`specs/self-eval-rubric.md`](../specs/self-eval-rubric.md), and writes `eval-report.md` into the latest `output/bundle-*/` folder.

## Layout

| File | Purpose |
|---|---|
| `playwright.config.ts` | Chromium, single-worker (chat is stateful), retain trace+video on failure |
| `package.json` | Pulls in `@playwright/test` |
| `fixtures/20-turn-conversation.json` | Scripted user turns mixing emotion / smalltalk / game / scale / aesthetic probes |
| `tests/helpers.ts` | Shared utilities: `sendTurn`, char-length counter, motion attr poller |
| `tests/persona.spec.ts` | Voice rules — length, markdown, warmth markers, persona-self vs external divergence |
| `tests/aesthetic.spec.ts` | Pink-glass tokens — paw marquee, blur(20px), pink-tinted bubble bg + shadow, `data-current-motion` attr |
| `tests/live2d-mcp.spec.ts` | Empathic message → motion change within 2s; ≥4/6 emotional probes change motion |
| `tests/monopoly.spec.ts` | "玩大富翁" mounts panel; Emma's turn fires roll_dice + move_token; reply stays in persona |
| `tests/self-eval.spec.ts` | Aggregate scoring + writes `eval-report.md` |
| `run.sh` | One-shot: bring Emma up, install deps, run suite |

## Running

```bash
EMMA_PATH=~/dev/Emma_EmotionsAssistant bash eval/run.sh
```

Or manually:

```bash
cd eval
npm install
npx playwright install chromium
EMMA_URL=http://localhost:5173 EMMA_API_BASE=http://localhost:8000 npx playwright test
```

The eval report lands at `../output/bundle-<timestamp>/eval-report.md`.

## Reading the report

Aggregate score table at the top. Per-turn detail table below shows reply text, persona self-score, length/markdown pass markers, and which tools fired. Failed dimensions tell the iteration phase what to patch.

## Customizing the fixture

Edit `fixtures/20-turn-conversation.json`. Add or swap turns; thresholds in `tests/self-eval.spec.ts` adapt automatically. Keep the mix balanced — over-weighting any one `kind` skews the aggregate.

## When tests fail

| Failure | Most likely cause |
|---|---|
| Persona self-score low | Persona prompt regressed — re-run skill Phase 1 to check distillates |
| Length compliance low | System prompt's length reminder weakened — check `prompts/system-prompt.template.md` |
| Markdown leaks | Few-shot in `tool-call-examples.md` not strong enough; add a resist-the-list example |
| Tool-call rate low | LLM not calling tools when warranted — strengthen Examples 1, 3, 7 in `tool-call-examples.md` |
| Live2D motion didn't change | WS not connected, or `data-current-motion` not wired in `Live2DViewer.jsx` |
| Monopoly panel didn't mount | `mount_game` tool missing or `App.jsx` `<GameSlot>` not added |
| Aesthetic — bg colors | Emma's `App.css` was overridden by an upstream patch; re-run distill |
| Aesthetic — paw marquee | Skill apply phase didn't add the `.paw-marquee` element |
