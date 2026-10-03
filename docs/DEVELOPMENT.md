# Development guide

Prerequisites: Python 3.11+, Node 20+ (npm), optionally Docker.

## First run
```bash
npm install                                   # web app + engine (npm workspaces)
pip install -r apps/api/requirements-dev.txt  # API + test tools (production needs only requirements.txt)
```

## Run the full stack (two terminals)
```bash
# 1. API (http://localhost:8100, docs at /api/docs). Port 8100 avoids clashing with other local projects.
cd apps/api
PRESCRIBBLE_DATABASE_URL=sqlite:///./prescribble.db python -m uvicorn app.main:create_app --factory --port 8100

# 2. Web app (http://localhost:5173, proxies /api to the API)
npm run dev:web
```
The web app also works **without** the API (offline mode): the Studio runs fully, accounts are hidden.

## Tests
```bash
cd apps/api && python -m pytest -q            # API: auth, validation, rate limits, migrations up/down
npm test                                      # engine golden tests (vs the Python pipeline) + web unit tests
npm run typecheck
npm run lint                                  # ESLint (typescript-eslint + react-hooks)
PW_CHANNEL=msedge npm run test:e2e            # Playwright smoke tests in an installed browser (chrome also works); CI: npx playwright install chromium
```
Regenerate the engine's golden fixtures after changing the Python pipeline: `python scripts/make_engine_fixtures.py`.

## Build and serve a static copy (also what a lab machine needs)
```bash
npm run build:web
python3 apps/web/serve.py                     # http://localhost:8765, SPA fallback, no backend (offline mode)
```

## Operator tasks
```bash
cd apps/api
python -m app.cli make-admin someone@example.com      # promote (the only way to become an admin)
python -m app.cli remove-admin someone@example.com
```

## The embeddable widget
`packages/widget` builds to one script (`npm run build:widget`; `npm run build:web` and `npm run dev:web` do it first). It is served from `/widget/prescribble-widget.js` and loads the model and runtime from the same host, so any page can embed it. See `/developers` for the user-facing docs.

## Single-origin mode (API serves the built web app)
```bash
npm run build:web
cd apps/api
PRESCRIBBLE_WEB_DIST=../web/dist PRESCRIBBLE_DATABASE_URL=sqlite:///./prescribble.db python -m uvicorn app.main:create_app --factory --port 8100
```
One process, one origin: `/` is the app, `/api/*` the API, clean URLs work after a refresh. Fingerprinted assets and versioned models are cached
immutably; fixed-name files (`ort/`, `index.html`) are revalidated.

## Docker
```bash
cp deploy/.env.example deploy/.env            # set SECRET_KEY (and COOKIE_SECURE=true behind HTTPS)
docker compose -f deploy/docker-compose.yml --env-file deploy/.env up --build
# optional PostgreSQL:  add  --profile postgres  and set POSTGRES_PASSWORD + DATABASE_URL in deploy/.env
```
The compose file validates (`docker compose config`); the image build itself has not been run on this machine yet (Docker Desktop was not running).

## Lab bundle for the new web app
```bash
npm run build:web && python scripts/make_web_bundle.py    # dist/prescribble-web.zip (~20 MB)
```
Unzip on any machine with Python 3 and run `bash run.sh` (or `run.bat`). No backend: the app runs in offline mode (Studio fully working).

## Database migrations
```bash
cd apps/api
alembic revision --autogenerate -m "describe change"    # then review the generated file
alembic upgrade head                                     # also runs automatically in dev
```

## Configuration (environment variables, prefix `PRESCRIBBLE_`)
| Variable | Default | Notes |
|---|---|---|
| `ENV` | `dev` | `prod` enforces a strong secret and secure cookies |
| `DATABASE_URL` | `sqlite:///./prescribble.db` | use Postgres in production |
| `SECRET_KEY` | random per process in dev | required (>= 32 chars) in prod |
| `CORS_ORIGINS` | `http://localhost:5173` | JSON list |
| `MODEL_VERSION` | `v1` | the model that scores daily-challenge attempts (needs `models/<version>/`) |
| `ML_ROOT` | auto | folder containing the `src` training-pipeline package (the Docker image places it in `/app`) |
| `ATTEMPTS_PER_DAY` | `3` | scored attempts per user per UTC day |
| `API_PER_MINUTE` / `API_DAILY_LIMIT` | `60` / `1000` | REST API limits per key (the daily limit is stored on each key when it is created) |
| `MAX_KEYS_PER_USER` | `5` | active API keys per account |
| `MAX_OPEN_ROOMS` / `MAX_ROOM_MEMBERS` / `MAX_ROUNDS_PER_ROOM` | `10` / `60` / `30` | classroom limits (see `docs/CLASSROOMS.md`) |
| `ROUND_MIN_S` / `ROUND_MAX_S` / `ROUND_GRACE_S` | `10` / `300` / `3` | round length range and the collection grace period |
| `JOINS_PER_MINUTE` | `20` | room joins per client IP |

## Model versions
`models/<version>/` holds `sketch.onnx`, `meta.json`, `results.json`, `samples.json`. The web build copies it into `public/models/`.
Ship a new model by adding `models/v2/` and bumping `MODEL_VERSION` in `apps/web/src/lib/engine.tsx`.
