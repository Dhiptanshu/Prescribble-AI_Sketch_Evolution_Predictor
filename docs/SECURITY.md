# Security review and threat-model checklist (Phase 7)

Scope: the web app, the API, the live-room WebSocket, the Docker image and the operator tools. Method: reading the code against the OWASP Top 10, a dependency audit, and a test for every control that matters (so a regression fails the build). **Not done: an external penetration test.** Status: ✅ in place and tested · ⚠️ accepted limit (explained) · ⬜ not built.

## 1. Accounts and sessions
| Threat | Control | Status |
|---|---|---|
| Stolen password database | argon2id hashes (library defaults); passwords are never logged (by reading the code: only method, path, status and timing are logged) | ✅ `tests/test_auth.py` |
| Guessing passwords | per-IP rate limit on register and login; equal work for unknown emails and wrong passwords (no timing oracle) | ✅ |
| Session theft by script | session is an **httpOnly** cookie (not readable by JavaScript), `Secure` in production, `SameSite=Lax` | ✅ |
| Cross-site request forgery | SameSite=Lax **plus** a server-side check: a write that carries the session cookie and a browser `Origin` from another site is refused (`bad_origin`). `PRESCRIBBLE_TRUSTED_ORIGINS` lists extra allowed origins (needed only if a proxy rewrites `Host`) | ✅ `tests/test_security.py` |
| Cross-site WebSocket hijacking | the live-room socket checks `Origin`; students authenticate with a token in the first message (never in the URL) | ✅ `tests/test_rooms.py` |
| Privilege escalation | admin is granted only by the server command line (`python -m app.cli make-admin`); signing up never grants it | ✅ |
| Weak production secret | the server refuses to start in `prod` with a key under 32 characters | ✅ |
| Session lifetime | a session token cannot be revoked server-side before it expires (14 days); logout deletes the cookie. Changing this needs a per-user session counter | ⚠️ |
| Account enumeration | registering an existing email says so (needed for a usable sign-up form); it is rate limited. There is no password-reset feature, so no reset-based leak | ⚠️ |

## 2. Data access
| Threat | Control | Status |
|---|---|---|
| Reading another user's data | every query is scoped to the signed-in user; other people's drawings, rooms and keys answer **404** (never 403) so ids cannot be probed | ✅ tests in `test_drawings`, `test_rooms`, `test_platform` |
| SQL injection | all database access goes through SQLAlchemy with bound parameters; no string-built SQL (the one raw `COUNT(*)` in backups uses a fixed table list) | ✅ |
| Guessing share links, room tokens, API keys | 72-bit share tokens, 192-bit room tokens and API keys; keys and room tokens are stored only as SHA-256 hashes | ✅ |
| API key abuse from a web page | a key is refused if the request carries a browser `Origin` | ✅ |
| Training on data without permission | consent off by default, confirmed labels only, no identity in exports, one-click withdrawal; classroom drawings are never training data | ✅ `tests/test_teach.py` |

## 3. Abuse and denial of service
| Threat | Control | Status |
|---|---|---|
| Huge request bodies | 1 MB cap enforced **while streaming** (a chunked upload with no length is cut off too), plus per-drawing limits on strokes and points | ✅ `tests/test_security.py` |
| CPU exhaustion through scoring | attempts per day, one submission per round, per-key burst and daily quotas, per-user write limits, per-IP join limit | ✅ |
| Guessing room codes | per-IP limit on joins; 31^6 (about 887 million) codes | ✅ |
| Scripted cheating on the leaderboard | implausibly fast drawings are stored but kept off the ranking (best effort, not a guarantee) | ⚠️ |
| Rate-limit state | counters live in the process: correct for one server; several servers would each count separately | ⚠️ |

## 4. Browser and transport
| Threat | Control | Status |
|---|---|---|
| Cross-site scripting | React escapes all output; no `dangerouslySetInnerHTML`, `innerHTML` or `eval` in the app or the widget; a strict **content security policy** on every page (own scripts only, WebAssembly allowed, no framing, no plugins) | ✅ `tests/test_security.py`; the browser tests would fail on any policy violation |
| Clickjacking, MIME sniffing, referrer leaks | `frame-ancestors 'none'` and `X-Frame-Options: DENY`, `nosniff`, `Referrer-Policy`, `Permissions-Policy` (no camera, microphone, location) | ✅ |
| Downgrade to http | `Strict-Transport-Security` is sent when the deployment is https-only (secure cookies). TLS itself is the host or proxy's job | ✅ / see DEPLOY.md |
| The API reference page | `/api/docs` loads its viewer from a CDN, so it is deliberately exempt from the policy | ⚠️ |

## 5. Supply chain and operations
| Item | Status |
|---|---|
| Python dependencies | `pip-audit` on `apps/api/requirements.txt`: **no known vulnerabilities** (3 Oct 2026; CI repeats it) ✅ |
| JavaScript dependencies | `npm audit --omit=dev`: **2 moderate**, both `react-router` "arbitrary constructor injection via `deserializeErrors()` in SSR hydration". This app is a client-only single-page app and never uses server-side rendering or that function, so it is not reachable. Fixing it means a major-version upgrade of React Router; CI fails only on high or critical ⚠️ |
| Secrets in git | `.env`, databases and keys are git-ignored. A search of every tracked file and of the whole history for secret-like assignments, key files (`.env`, `.pem`, `kaggle.json`...) and private-key blocks found none (3 Oct 2026) ✅ |
| Container | non-root user, no build tools in the final image, health check, data on a volume. CI builds the image and `scripts/verify_deploy.py` checks the running container (see DEPLOY.md) |
| Backups | `python -m app.cli backup` (consistent, verified, pruned) and `restore`, tested including a backup taken while the app writes ✅ |
| Logging | access log has method, path, status and timing; no bodies, cookies or passwords. Paths of shared drawings contain their share token (anyone who can read the log can open those links) ⚠️ |
| Admin dashboard | admin only; owners shown by display name, never by email ✅ |
| Teacher moderation | no way for a teacher to remove a student and no nickname filter ⬜ |
| WebSocket frame size | uvicorn is started with `--ws-max-size 65536` in the image ✅ |

## 6. Not covered
An external penetration test; a formal privacy-law review (GDPR and similar: the consent, export and delete features exist, but nobody has checked them against a particular law); the host's own security (patching, firewall, TLS certificates).
