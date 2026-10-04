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
| **2. Accounts & persistence** (done) | Save drawings, gallery, personal stats, share links, replay export (WebM) | A user's history and stats persist and are computed from real records |
| **3. Compete** (done) | Daily challenge, server-side verification, leaderboard, streaks | Scores are reproducible from stored strokes |
| **4. Platform** (done) | `/v1/predict`, API keys, usage metering, rate limits, docs page, embeddable widget, admin metrics | A third-party page can embed the widget with a key |
| **5. Classrooms** (done) | Rooms, live race, teacher view (WebSocket) | Two browsers play a synchronised round |
| **6. Model flywheel** (built; real-user gain not yet measured) | Opt-in feedback, dataset export, retrain on Kaggle, model registry/versions, scale to 100+ classes, mouse-drawing adaptation | New model version ships without touching app code; measured gain on real user drawings |
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

**Phase 2 done (saved drawings, gallery, stats, sharing, video export)**
- **API:** `drawings` table (migration 0002, cascade delete), create / list (cursor pagination) / get / relabel / delete, share links (72-bit tokens, revocable, public page exposes only strokes, label, AI result, date and display name), `GET /me/stats`, export includes drawings. The server recomputes stroke count and ink length (never trusts the client), validates class names against the model's own `meta.json`, caps drawing size (strokes, points, 1 MB body), enforces a 200-drawing quota and per-user write rate limits. Other users' drawings answer 404, not 403. **47 API tests pass.**
- **Web:** Save panel in the Studio (label defaults to the AI's guess; the "AI had it by X% of the ink" figure comes from the predictions that actually ran while drawing), Gallery with pagination, drawing page (real-model replay, relabel, share/unshare, delete), public share page, Stats page (tiles, 30-day activity chart, per-object table; honest empty states), replay export to a real `.webm` video recorded from the player canvas. 19 unit tests (incl. the recognition-point maths).
- **End-to-end:** 16 Playwright tests in real Edge, including the whole journey of one drawing (save, replay, relabel, share, stranger views it, revoke, video download is a real file, stats, delete) and an intruder blocked from another user's drawing.
- Honest limit: the recognition point is client-reported and therefore unverified; Phase 3 recomputes scores on the server for anything competitive.

**Phase 3 done (daily challenge, server-verified scores, leaderboard, streaks, settings)**
- **Scoring is the server's job.** The API runs the same ONNX model and the same stroke-pipeline code as training (`src/data/partial.py`, imported, not re-implemented). It cuts a submitted drawing at 5% steps of its ink and scores by how early the AI's #1 guess is the day's word with at least 50% confidence: 100 at 5% of the ink down to 5 at 100%, 0 if never. The browser only displays the result.
- **Measured, not assumed:** the server pipeline on 90 real held-out sketches gives Top-5 91.1% at 20% of the ink, 94.4% at 30%, and Top-1 91.1% on finished drawings, matching the model's published results (90.6 / 94.3 / 91.6). A test fails if it drifts below 80%.
- **Daily word:** HMAC of the date with the server secret (unpredictable ahead of time), never the same word two days in a row, frozen in the database on first request.
- **Fairness:** 3 attempts per user per UTC day, best counts; submissions drawn implausibly fast (under 0.4 s, or an impossible pen speed, or no time reported) are stored and flagged but kept off the leaderboard, and the player is told. This is best-effort against scripts, not a guarantee.
- **Leaderboard:** ranked in SQL (window function), ties broken by who got there first, one row per player, previous days available, no emails or ids exposed. Players can hide their name (they keep their rank and show as "Anonymous").
- **Streaks and record:** `GET /challenge/me` (current and longest streak, best, average, history).
- **Settings page:** display name, leaderboard visibility, training consent (off by default), download my data, delete my account.
- **Tests:** 75 API (incl. leaderboard rules, privacy, day rollover with an injected clock, cascade delete), 21 web unit, 20 Playwright e2e (incl. scoring a real held-out sketch through the UI, three attempts then lock, privacy toggle, and an instant scripted submission being kept off the board).
- Found by the e2e tests and fixed: a heading whose `aria-label` hid the word from screen readers, and a post-deletion redirect that went to /login instead of home.

**Phase 4 done (developer platform: widget, REST API, keys, metering, admin)**
- **Two integration paths, matching the privacy stance.** The **widget** (`<script>` tag or `<prescribble-canvas>`, 60 kB) runs the model inside the visitor's own browser: no key, nothing to host, and the drawing never leaves the page. The **REST API** (`POST /api/v1/predict`) is for backends and other languages and uses **secret keys**.
- **Keys:** 192-bit random, shown once, stored only as a SHA-256 hash, revocable instantly, up to 5 active per account. Requests that carry a browser `Origin` header are refused (`browser_not_allowed`), so a key leaked into front-end code cannot be abused from a web page. A key is not a login and a login is not a key.
- **Limits and metering:** per-key burst limit (60/min) and daily quota (1000, resets at midnight UTC) with `Retry-After` and `RateLimit-*` headers; real per-key, per-day counters (requests, errors, model time) feed a usage chart and the admin dashboard. The limits shown in the docs are read from the live settings.
- **Admin:** `GET /admin/metrics` and an Operations page (accounts, drawings, challenge players and flagged attempts, active keys, 14-day request chart, busiest keys by owner name). Admins are promoted only by the server CLI (`python -m app.cli make-admin <email>`); signing up never grants it.
- **Developer docs page** (`/developers`): live widget demo loaded exactly as a customer would load it, cURL / Python / Node examples, error-code table, and a key manager. The example request/response is **captured from the real model** and an API test fails if it ever drifts.
- **Cross-origin hardening:** widget script, model and WebAssembly runtime are served with CORS only under `widget/`, `models/`, `ort/`; the app's own files stay same-origin.
- **Tests:** 99 API, 34 unit (engine 6, widget 7, web 21), 25 Playwright e2e. The embed test hosts a "customer site" on a separate real origin and asserts from the network log that the widget makes no request carrying data and talks to no third host. (A fake in-browser document is refused localhost access by Edge's local-network protection, so the test uses a real second server.)

**Phase 5 done (classrooms: rooms, live rounds, teacher view)**
- Teachers (accounts) open rooms; students join with a 6-character code and a nickname, no account (room token, hash stored). Rounds have one word and a timer; students draw while the AI guesses live in their own browser, and the server scores the handed-in drawing with the daily-challenge scorer. Scores are hidden until the round ends, then ranking, the AI's record on the round (how many drawings it named, typical ink fraction), everyone's drawings and class standings are shown.
- Realtime over a WebSocket (`/rooms/{id}/live`): teacher by cookie, student by first-message token, Origin checked; the web client reconnects and falls back to HTTP re-reads. Round phases are derived from timestamps, timers only trigger pushes. Details, limits and the single-process caveat: `docs/CLASSROOMS.md`.
- **Tests:** 130 API (31 new), 27 web unit (6 new), 23 full-product Playwright in real Edge (2 new: teacher plus two students in separate browser profiles through a whole round, and a stranger refused). Found by the e2e test and fixed: a student page re-sent an already handed-in drawing when the clock hit zero (server refused with 409).
- Not done: student removal and nickname moderation, load test with a full class, multi-replica fan-out (needs Redis pub/sub).

**Phase 6 built (model flywheel; details, data rules and results in `docs/FLYWHEEL.md`)**
- **A new model version ships without touching app code.** `models/registry.json` names the live version; the API, the web app and the widget all read it (the file is never cached). Registration hashes the ONNX file, and promotion is **gated**: the candidate must run, must not drop a class, and must not be worse than the live model (tolerance 1 point Top-5) on held-out sketches of the shared classes, plus on held-out real user drawings once there are 30. Rollback and a recorded `--force` exist. A challenge day or classroom round keeps its own model when the live one changes. Tests: 13 registry, 8 API (version switching, pinning, reload, caching, parity between the gate's scorer and the server's), 3 web unit, 3 widget unit, and a browser test that promotes a version on disk and watches the app load it.
- **Consent-gated feedback.** Training-ready = owner's consent on now + a label the person confirmed + a class of the live model + not a duplicate. New fields on drawings (confirmed label, pointer type: mouse/touch/pen). `python -m app.cli export-training` writes JSONL with no account identity and a stable train / held-out split. Admin dashboard tile with the counts. 14 API tests, 5 mix/split tests.
- **Teach the AI page** (`/teach`): explicit consent, then the word with the fewest examples, saved as a confirmed drawing with its pointer type; kept out of gallery and stats; own quota; one-click withdrawal.
- **All 345 QuickDraw categories (v3, live):** class sets `v1`/`v2`/`v3` (`src/classsets.py`), packed memory-mapped sketch storage (8.3 M training drawings), a wider model, trained on a Kaggle GPU: Top-5 62.3% at 30% of the ink and 93.2% on the finished drawing over 345 classes; on the original 30 classes v3 beats v1 (95.4% vs 92.8% Top-5, both limited to those classes). More classes make each prediction harder (v3 free to answer with any class scores 66.1% on those 30 classes' sketches). v2 (100 classes) was the intermediate step. Details and per-class results: `docs/FLYWHEEL.md`, `report/GENERATIONS.md`.
- **A training bug found and fixed:** every epoch replayed the same samples, so all models trained earlier (v1, v2, the first v3, the VGG / ResNet comparisons) saw only a fixed subset; the retrained v3 gained 10 points of Top-5 at 30% of the ink. v1 and v2 were not retrained.
- **Mouse-drawing adaptation:** fine-tuning with user drawings mixed in and a before / after measurement on the held-out real drawings and on QuickDraw (`src/flywheel/finetune.py`, `kaggle/flywheel/run_finetune.py`). Only smoke-tested: it needs real drawings, and nobody has taught the AI yet.
- Found by the tests and fixed: the Teach page kept showing the old contribution count after a withdrawal.

**Phase 7 built (hardening; checklist in `docs/SECURITY.md`, deployment in `docs/DEPLOY.md`)**
- **Security:** strict content security policy and security headers, a cross-site write check (`OriginGuard`), a request-body cap enforced while streaming, WebSocket frame cap; dependency audit (`pip-audit` clean; 2 moderate `npm audit` findings in react-router, not reachable in a client-only app, documented). Tests in `test_security.py`.
- **Operations:** verified SQLite backups and restore in the operator CLI (`backup`, `restore`), SQLite in WAL mode, scoring limited to one ORT thread per session with a concurrency semaphore (predict throughput 8 to about 20 a second, 95th percentile 7.5 s to under 0.7 s under 16 callers), `scripts/verify_deploy.py` smoke test, GitHub Actions workflow (6 jobs), accessibility scan of every main page in both themes (axe, WCAG 2.1 A and AA).
- **Load test** (`scripts/loadtest.py`, numbers in `docs/DEPLOY.md` section 6): 60 students handing in at the same instant are all scored in about 20 s (CPU bound, about 3 a second), 0 errors. A first run suggested 30x worse; the cause was the test tool opening a new TCP connection per request on Windows, fixed in the tool.
- **Found and fixed on the way:** the Docker image crashed on start (import path assumptions, missing `classsets.py`), now covered by `test_inference_paths.py`.
- **Not verified, said plainly:** the fixed Docker image has not been run (Docker Desktop's storage went read-only; restarting it would stop your other project's containers, so it waits for your OK); the CI workflow has never run on GitHub; nothing was tested on Linux or PostgreSQL; no external penetration test. Open: teacher removing a student, nickname moderation, Redis fan-out for several replicas.

**Next:** deploy (owner picks the host), the Docker check above, and the open leftovers.

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
