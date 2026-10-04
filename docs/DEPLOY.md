# Deploying Prescribble

Hosting-agnostic: anything that runs a Docker container (a small VPS, a container service, your own machine). **Choosing the provider is an open decision for the owner**; nothing here depends on it.

## What you are deploying
One image (`deploy/Dockerfile`): the API plus the built web app, one process, port 8100. The model runs in each visitor's browser; the server only needs CPU for accounts, rooms and scoring. Data (accounts, drawings, rooms) lives in a SQLite file on the `/data` volume (or PostgreSQL, see below). A visitor's first load downloads about 45 MB (the model and the WebAssembly runtime), cached afterwards.

## 1. Configure
```bash
cp deploy/.env.example deploy/.env
```
| Variable | Meaning |
|---|---|
| `SECRET_KEY` | **required**, 32+ random characters (`python -c "import secrets; print(secrets.token_urlsafe(48))"`). Signs sessions; changing it signs everyone out. The server refuses to start in production without it |
| `COOKIE_SECURE` | `true` behind HTTPS (always, in production). Also switches on the `Strict-Transport-Security` header |
| `DATABASE_URL` | default `sqlite:////data/prescribble.db`; PostgreSQL: see below |
| `TRUSTED_ORIGINS` | JSON list, e.g. `["https://prescribble.example"]`. Only needed if your proxy rewrites the `Host` header (otherwise sign-in works but writes are refused as cross-site) |
| `FORWARDED_ALLOW_IPS` | the reverse proxy's address. Without it every visitor appears to come from the proxy and the per-IP limits (sign-in attempts, room joins) apply to everyone together |

## 2. Run
```bash
docker compose -f deploy/docker-compose.yml --env-file deploy/.env up -d --build
python scripts/verify_deploy.py http://localhost:8100 --restart-container <container name>     # see section 5
```
Put a reverse proxy with TLS in front (Caddy, nginx, a platform's load balancer). It must pass WebSocket upgrades on `/api/v1/rooms/<id>/live` and send `Host`, `X-Forwarded-For`, `X-Forwarded-Proto`. **Run exactly one container**: live classroom rooms keep their sockets in memory (and the rate limits their counters), so two replicas would split rooms and double every limit.

## 3. Operate
| Task | Command |
|---|---|
| Make someone an admin | `docker compose exec app python -m app.cli make-admin someone@example.com` |
| **Back up** the database | `docker compose exec app python -m app.cli backup --out /data/backups --keep 14` (consistent even while the app writes, verified after writing, keeps the newest 14). Copy `/data/backups` somewhere else on a schedule (cron + `docker cp`, or mount that folder from the host) |
| Restore | stop the app, `python -m app.cli restore --from /data/backups/prescribble-<stamp>.db`, start it (the replaced file is kept as `.before-restore`) |
| Ship a new model | add `models/vN/`, `python -m src.flywheel.registry register vN`, `promote vN --heldout ...` (accuracy-gated), rebuild the image (`models/` is baked in), then it is live. `POST /api/v1/admin/model/reload` switches a running server without a restart. Details: `docs/FLYWHEEL.md` |
| Update the app | `git pull`, `docker compose up -d --build` (the volume keeps the data; migrations run on start) |
| Look at the logs | `docker compose logs -f app` (method, path, status, time; no bodies or cookies) |

PostgreSQL instead of SQLite: `docker compose --profile postgres ... up`, set `POSTGRES_PASSWORD` and `DATABASE_URL=postgresql+psycopg://prescribble:<password>@db/prescribble` in `deploy/.env`. Back it up with `pg_dump` (`app.cli backup` is SQLite only). Not tested against a real PostgreSQL in this project: the migrations are written to be portable but have only run on SQLite.

## 4. What it costs
Roughly $5-15 a month for a small instance (1 vCPU, 1-2 GB) plus about $10-15 a year for a domain; bandwidth is the other term (about 45 MB per new visitor, about $0 behind a free CDN tier). A classroom of 60 students submitting together wants 2 vCPUs. Model training uses Kaggle's free GPU hours. These are estimates from the app's measured needs, not quotes.

## 5. Verifying a deployment
`python scripts/verify_deploy.py <url> [--restart-container <name>]` creates a throwaway account on that server and checks: health, the app and its security headers, deep links, the model files and their caching, the API and the web app agreeing on the live model, sign-up, saving a drawing, the cross-site write refusal, the prediction API with a key (and its refusal from a browser), today's challenge word, the live classroom WebSocket, and (with `--restart-container`) that the data survives a restart. It deletes the account at the end. CI runs it against the freshly built image.

## 6. Capacity (measured on a development laptop; see `docs/results/loadtest.json`)
Measured with `scripts/loadtest.py` against one server process (model v3, 345 classes) on an 8-core Ryzen laptop running Windows, with the rate limits raised. Your hardware will differ; the raw output is `docs/results/loadtest.json`.

| Scenario | Result |
|---|---|
| Prediction API, 16 concurrent callers, 20 s | about 17-20 predictions/s, 0 errors, median 0.25 s, 95th percentile 0.5-0.7 s |
| Classroom: 60 students join, then all hand in at the same instant | joins 0.6-0.8 s; round start reaches all 60 live screens in under 1 s; **all 60 hand-ins scored and shown on the teacher's screen in 20-21 s** (about 3 a second; median student waits 12 s), 0 errors |
| Daily challenge: 50 simultaneous scored attempts | 0 errors, median 4.9 s, 95th percentile 7.3 s |

Reading these: scoring one drawing across its timeline is the CPU cost (about 0.3 s of one core), so a class handing in at the exact same second queues; a class that draws for a minute and hands in spread out sees about a second. The 99th-percentile predict latency (about 10 s) is the test's first connections, not scoring. **Test-tool caveats:** on Windows, opening many *new* TCP connections at once is slow (about 1 s each), which first made this server look 30x slower than it is; the test now reuses connections as a browser does. Not measured: Linux, more than one core's worth of parallel load, PostgreSQL, and real browsers.

## 7. Known limits
One server only (rooms and rate limits are in memory); no automatic off-machine backup (you schedule the copy); sessions cannot be revoked before they expire; TLS, patching and firewalling are the host's job. See `docs/SECURITY.md`.
