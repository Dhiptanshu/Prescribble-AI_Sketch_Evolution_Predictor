# Development guide

Prerequisites: Python 3.11+, Node 20+ (npm), optionally Docker.

## First run
```bash
npm install                                   # web app + engine (npm workspaces)
pip install -r apps/api/requirements.txt      # API
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
```
Regenerate the engine's golden fixtures after changing the Python pipeline: `python scripts/make_engine_fixtures.py`.

## Build and serve a static copy (also what a lab machine needs)
```bash
npm run build:web
python3 apps/web/serve.py                     # http://localhost:8765, SPA fallback, no backend (offline mode)
```

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

## Model versions
`models/<version>/` holds `sketch.onnx`, `meta.json`, `results.json`, `samples.json`. The web build copies it into `public/models/`.
Ship a new model by adding `models/v2/` and bumping `MODEL_VERSION` in `apps/web/src/lib/engine.tsx`.
