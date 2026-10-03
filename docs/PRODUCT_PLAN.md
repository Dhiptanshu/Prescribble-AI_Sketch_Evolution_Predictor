# Product plan: from lab POC to a SaaS product

Working product name: **Prescribble** (placeholder; one constant, `APP_NAME`, to change). Tagline: *the AI that guesses your drawing before you finish it.*

## 1. Product

One recognition engine, three surfaces:

| Surface | Who | Value |
|---|---|---|
| **Studio + Daily Challenge** | Everyone | Draw, watch the AI guess early, keep a gallery, streaks, leaderboard, shareable replays |
| **Developer platform** | Game / ed-tech developers | REST API + embeddable widget: "guess as the user draws" as a service |
| **Classrooms** | Teachers | Live rooms where students draw and the AI races them |

Differentiators (all real, none mocked): early recognition from 10–30% of the ink, a ghost of the predicted ending, per-user "recognisability" stats, privacy by default (the model runs in the browser; strokes are stored only if the user saves them).

## 2. Principles
1. **Privacy first.** Inference runs client-side. The server stores a drawing only when the user saves or submits it. Training use is opt-in, off by default. Account data export and delete are built in.
2. **Server is the source of truth for anything competitive.** Scores are recomputed server-side from submitted strokes with the same ONNX model (no trusting the client).
3. **Works offline / guest.** The Studio works with no account and no network once loaded (needed for the lab).
4. **No fake data anywhere.** Empty states instead of placeholders. Every stat and chart comes from real records.
5. **Small, traversable modules; typed boundaries; tests with every feature.**

## 3. Architecture

```
src/, kaggle/, notebooks/, report/     ML research + training (existing, unchanged)
packages/engine/    TypeScript: stroke pipeline (RDP, raster, sequence) + ONNX Runtime Web model wrapper
packages/widget/    embeddable <script> widget built on the engine
apps/web/           React + TypeScript + Vite SPA: marketing site and the app
apps/api/           FastAPI service: auth, drawings, challenges, leaderboard, API keys, predict, admin, rooms (WebSocket)
models/             versioned model artefacts (onnx + meta + results) served as immutable static files
deploy/             Dockerfiles, docker-compose, env templates
docs/               plans, API docs, ADRs
scripts/            bundle (lab), bundle self-check, fixtures, notebooks, dataset staging
```

- **API:** Python 3.11, FastAPI, SQLAlchemy 2 + Alembic, SQLite in dev and Postgres in production, bcrypt, JWT in an httpOnly cookie, hashed API keys, rate limiting, structured logging, `/healthz` and `/metrics`.
- **Server-side inference:** `onnxruntime` + the canonical Python pipeline (`src/data/partial.py`), used for score verification and the public predict API.
- **Web:** React 18, TypeScript, Vite, React Router, TanStack Query, design tokens (existing look: dark/light, purple-cyan accent). Static build is deployable anywhere and works without the API (guest mode).
- **Realtime:** FastAPI WebSockets for classrooms.

### Core data model
`users`, `drawings` (strokes, mode, prompt, model_version, recognised_at_fraction, final Top-5, share token, public flag),
`challenges` (date → class, deterministic), `scores` (best per user per challenge), `api_keys` (prefix + sha256 hash, quota, revoked_at),
`usage_events` (real metering), `feedback` (label corrections, consent-gated), `rooms`, `room_members`.

### Scoring ("recognisability")
Server cuts the submitted drawing at every 5% of its ink length, runs the model, and finds the first fraction where the target is the Top-1 guess with p ≥ 0.5.
Score = `round((1 - fraction) * 100)`; a drawing the AI never gets scores 0. Plausibility checks (duration, point count, stroke timing) flag pasted or machine-made input.

## 4. Roadmap (each phase ships working software with tests; no calendar, quality gates instead)

| Phase | Scope | Done when |
|---|---|---|
| **1. Foundation** | Monorepo, API skeleton (config, DB, migrations, auth, health), engine package, web shell + design system, Studio ported with guest mode | Register/login works end to end, Studio runs from the new app, API and engine tests green |
| **2. Accounts & persistence** | Save drawings, gallery, personal stats, share links, replay export (WebM) | A user's history and stats persist and are computed from real records |
| **3. Compete** | Daily challenge, server-side verification, leaderboard, streaks | Scores are reproducible from stored strokes |
| **4. Platform** | `/v1/predict`, API keys, usage metering, rate limits, docs page, embeddable widget, admin metrics | A third-party page can embed the widget with a key |
| **5. Classrooms** | Rooms, live race, teacher view (WebSocket) | Two browsers play a synchronised round |
| **6. Model flywheel** | Opt-in feedback, dataset export, retrain on Kaggle, model registry/versions, scale to 100+ classes, mouse-drawing adaptation | New model version ships without touching app code; measured gain on real user drawings |
| **7. Launch hardening** | Docker/compose, CI, security review, load test, accessibility pass, docs, backups | Clean `docker compose up`, CI green, threat-model checklist ticked |

### Progress (paused after Phase 1, core)
**Done and verified**
- Monorepo layout: `apps/api`, `apps/web`, `packages/engine`, `models/v1`.
- **API:** config (prod guard on the secret), SQLAlchemy models, Alembic migration (up/down tested), argon2 password hashing, JWT in an httpOnly cookie, register / login / logout / profile / export / delete-account, per-IP auth rate limit, one error shape, request ids, `/healthz`. **16 tests pass.**
- **Engine (TypeScript):** stroke pipeline + ONNX Runtime Web wrapper. **Golden tests against the Python training pipeline pass** (sequence features identical on real sketches).
- **Web (React + TS + Vite):** landing page with a live hero demo (real held-out sketch through the real model, stats read from the model's measured results), Studio (free draw, AI challenge, real-sketch replay, ghost, confidence timeline), register / login / sign-out, light and dark themes, offline mode when no backend is reachable. Production build 89 kB gzipped; type-check clean; 6 unit tests pass.
- Checked by hand in a real browser: Studio predictions identical to the POC, registration, session persistence across reloads, sign-out.

**Phase 1 completed since the first pause**
- `/auth/session` (always 200) replaces the 401 probe, so logged-out visitors see no console error.
- The API can serve the built web app itself (SPA fallback, safe paths, explicit media types, correct cache policy). **29 API tests pass.**
- Found and fixed in real-browser testing: the host's mime registry served `.mjs` as `text/plain` (browsers refuse that for module scripts), and an `immutable` cache header made the bad response stick. Fixed-name files are now revalidated; tests cover both.
- Engine `pipeline` subpath export so pure helpers never pull in the ONNX runtime (this made the hooks testable). **13 web tests pass** (API client, GuessPanel, prediction-loop scheduling) plus 6 engine golden tests.
- ESLint (typescript-eslint, react-hooks): clean. Type-check: clean.
- Dockerfile (multi-stage, non-root, healthcheck) and compose (SQLite volume, optional Postgres profile). Compose validated; **the image has not been built yet** because Docker Desktop was not running.
- Lab bundle from the new web app (`scripts/make_web_bundle.py`, ~20 MB). Verified both ways in a real browser: API single-origin and the static server with no backend (offline mode).

**Since then:** legacy `demo/` retired (the web app's offline mode and `scripts/make_web_bundle.py` replace it; `scripts/verify_web_bundle.py` self-checks the bundle; runbook in `docs/LAB.md`). Playwright smoke suite added: 11 tests in real Edge across the full product (API serving the app) and offline mode (static server, no backend). Model artefacts now live only in `models/<version>/` (`--version` flag on the export scripts).

**Left over:** build the Docker image once Docker Desktop is running; one real lab rehearsal when possible (the lab runbook lists what is untested).

**Next:** Phase 2 (save drawings, gallery, stats, share links, replay export).

## 5. Quality bars
- Backend: pytest with an isolated DB per test; auth, ownership and validation covered; migrations tested up and down.
- Engine: golden-fixture tests against the Python pipeline (sequence features exact; raster within tolerance).
- Web: type-checked, lint-clean, Vitest for logic, Playwright smoke for the main flows.
- Accessibility: keyboard reachable controls, contrast checked in both themes, reduced-motion respected.
- Performance budget: prediction update < 50 ms, first interactive < 3 s on a lab-class machine.
- Security: OWASP basics (hashing, rate limits, input limits, CORS, cookie flags, no secrets in git).

## 6. Decisions that are yours (defaults applied until you change them)
1. Product name (`Prescribble` is a placeholder).
2. Public hosting: needs an account on a host you pick (Render, Fly.io, a VPS). Everything runs locally and in Docker until then.
3. Email sign-in only to start. Google/GitHub OAuth needs client credentials you would create.
4. Billing: not building real payments. A plan/quota model is included for the API; Stripe (test mode) can be added later if you want it.
