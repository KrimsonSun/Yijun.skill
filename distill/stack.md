# Stack — Emma canonical

This file pins Emma's stack. Anything emitted by the skill **must** match. Drift is the failure mode this file exists to prevent.

> Last distilled from: `frontend/package.json`, `backend/requirements.txt`, `backend/mcp/server.py`, `docker-compose.yml`. Re-run Phase 1 to refresh.

---

## Frontend

| Component | Pinned to | Why locked |
|---|---|---|
| React | 18.2.x | Concurrent features used by `Live2DViewer.jsx` Suspense boundary |
| Vite | 5.x | Dev server speed; HMR config tuned for `.jsx` |
| Language | **plain `.jsx`** | No TypeScript. `@types/react` is dev-only for editor hints. |
| Styling | **vanilla CSS** | Per-component CSS in `frontend/src/styles/`. CSS variables in `App.css`. |
| HTTP | axios 1.6.x | `frontend/src/api.js` and `frontend/src/api/mcpClient.js` use shared instance |
| State | React Context API | No Redux, no Zustand, no Jotai |
| Live2D | `pixi-live2d-display@0.4.0` + `pixi.js@6.5.10` | Cubism 2.1 model "shizuku" (Emma) |
| i18n | `frontend/src/i18n.js` (custom `getT()`) | No `react-i18next` |

### Forbidden frontend substitutions

- ❌ TypeScript (`.tsx`, `tsconfig.json` for runtime, `@types/*` as runtime deps)
- ❌ Tailwind, Material UI, Chakra, Bootstrap, styled-components, emotion
- ❌ Next.js, Remix, Astro
- ❌ Redux, Zustand, MobX, Jotai, Recoil
- ❌ React Query, SWR (axios + Context covers it)
- ❌ Cubism 4 / `live2dcubismcore.js` model swap (the backup at `emma_backup_20251202_230151/` is intentionally unused)

If a new feature seems to require something on this list, ask Yijun before introducing it.

---

## Backend

| Component | Pinned to |
|---|---|
| FastAPI | 0.104.x |
| SQLAlchemy | 2.0.x |
| Pydantic | 2.5.x |
| Database | PostgreSQL (psycopg2 + pg8000 drivers) |
| Auth | passlib argon2 + python-jose JWT |
| LLMs | OpenAI Python SDK + `google-generativeai >= 0.8.0` |
| MCP | **Hand-rolled** in `backend/mcp/server.py` (Python dataclasses + enums) |

### Backend conventions

- Routes split by domain in `backend/api/routes/`: `admin.py`, `chat.py`, `conversations.py`, `history.py`, `live2d.py`, `mcp.py`, `scales.py`, `settings.py`, `users.py`.
- Services pattern: `backend/services/llm_service.py`, `backend/services/scale_service.py`. New cross-cutting logic lands as a service, not in the route handler.
- snake_case Python, PascalCase Pydantic models, kebab-case shell scripts.
- Comment density is **low**. Yijun's existing code has minimal docstrings; match that. Don't add multi-paragraph comments to emitted patches.

### Forbidden backend substitutions

- ❌ Official `mcp` Python SDK (`pip install mcp`) — extend `backend/mcp/server.py` instead
- ❌ Replacing `psycopg2` with `asyncpg` (the SQLAlchemy 2 setup is sync sessions)
- ❌ Switching from FastAPI to Flask/Django
- ❌ Replacing the custom `i18n.js` pattern with `python-babel`-driven server-side translation

---

## Infrastructure

- Docker + docker-compose for local
- AWS RDS / ALB scripts in `aws-deploy/` (4 numbered shell scripts)
- Cloud Run Dockerfiles exist but unused for Emma (used by AutoArxivSummarization)

---

## Testing

Currently: **no tests**. The skill introduces Playwright E2E in `eval/` (this skill repo, not in Emma). Backend unit tests are out of scope until Yijun asks.

---

## When the stack must drift

If a future feature genuinely needs something on the forbidden list (e.g. WebRTC for voice chat may push toward a different state library), the skill's iteration loop should:
1. Stop.
2. Ask Yijun explicitly.
3. Update this file before emitting any patch.

The skill should never silently introduce a forbidden dependency.
