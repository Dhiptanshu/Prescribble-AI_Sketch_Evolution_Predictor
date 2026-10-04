"""FastAPI application factory."""
import logging
import time
import uuid
import threading
from collections.abc import Callable
from contextlib import asynccontextmanager
from datetime import datetime, timezone

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware

from app import models as _models  # noqa: F401  (registers the tables on Base.metadata)
from app.config import Settings, get_settings
from app.db import Base, make_engine, make_session_factory
from app.errors import install_error_handlers
from app.middleware import BodyLimit, OriginGuard, SecurityHeaders
from app.ratelimit import SlidingWindowLimiter
from app.services.room_hub import RoomHub
from app.routers import admin, auth, challenge, drawings, health, keys, predict, public, rooms, stats, teach

API_PREFIX = "/api/v1"
MAX_BODY_BYTES = 1_000_000      # API requests above this are refused before parsing (drawings are well under 100 KB)
log = logging.getLogger("prescribble.access")


def create_app(settings: Settings | None = None, clock: Callable[[], datetime] | None = None) -> FastAPI:
    """`clock` returns the current UTC time; tests inject their own to simulate days."""
    settings = settings or get_settings()
    engine = make_engine(settings.database_url)

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        yield
        app.state.hub.shutdown()
        engine.dispose()

    app = FastAPI(title=settings.app_name, version="0.1.0", lifespan=lifespan,
                  docs_url="/api/docs", openapi_url="/api/openapi.json", redoc_url=None)
    app.state.settings = settings
    app.state.engine = engine
    app.state.session_factory = make_session_factory(engine)
    app.state.auth_limiter = SlidingWindowLimiter(settings.auth_attempts_per_minute)
    app.state.write_limiter = SlidingWindowLimiter(settings.writes_per_minute)
    app.state.public_limiter = SlidingWindowLimiter(settings.public_reads_per_minute)
    app.state.api_limiter = SlidingWindowLimiter(settings.api_per_minute)
    app.state.join_limiter = SlidingWindowLimiter(settings.joins_per_minute)
    app.state.hub = RoomHub(app)
    app.state.clock = clock or (lambda: datetime.now(timezone.utc))
    app.state.scorers = {}                       # scorers of non-live versions, kept so a running challenge or round finishes on its own model
    app.state.scorer = None                      # loaded on first use (see routers/challenge.py)
    app.state.scorer_lock = threading.Lock()

    if settings.env == "test":
        Base.metadata.create_all(engine)
    elif settings.auto_migrate:
        from app.migrations import run_migrations
        run_migrations(settings.database_url)

    app.add_middleware(BodyLimit, max_bytes=MAX_BODY_BYTES)
    app.add_middleware(CORSMiddleware, allow_origins=settings.cors_origins, allow_credentials=True,
                       allow_methods=["GET", "POST", "PATCH", "DELETE"], allow_headers=["Content-Type", "Authorization"])

    @app.middleware("http")
    async def request_context(request: Request, call_next):
        rid = request.headers.get("x-request-id") or uuid.uuid4().hex[:12]
        t0 = time.perf_counter()
        response = await call_next(request)
        response.headers["X-Request-ID"] = rid
        log.info("%s %s -> %s in %.1f ms [%s]", request.method, request.url.path, response.status_code,
                 (time.perf_counter() - t0) * 1000, rid)
        return response

    # outermost first: security headers, the cross-site check, then CORS and the request log (added above). The body cap is added FIRST, i.e. innermost, below
    # the request log: that log is a BaseHTTPMiddleware, which would turn an error raised from outside it while the body is read into a generic 400.
    app.add_middleware(OriginGuard, cookie_name=settings.cookie_name, trusted=[*settings.cors_origins, *settings.trusted_origins])
    app.add_middleware(SecurityHeaders, hsts=bool(settings.cookie_secure))

    install_error_handlers(app)
    app.include_router(health.router)
    app.include_router(auth.router, prefix=API_PREFIX)
    app.include_router(auth.me_router, prefix=API_PREFIX)
    app.include_router(stats.router, prefix=API_PREFIX)
    app.include_router(drawings.router, prefix=API_PREFIX)
    app.include_router(challenge.router, prefix=API_PREFIX)
    app.include_router(keys.router, prefix=API_PREFIX)
    app.include_router(predict.router, prefix=API_PREFIX)
    app.include_router(rooms.router, prefix=API_PREFIX)
    app.include_router(teach.router, prefix=API_PREFIX)
    app.include_router(admin.router, prefix=API_PREFIX)
    app.include_router(public.router, prefix=API_PREFIX)
    if settings.web_dist:
        from app.web import install_web
        install_web(app, settings.web_dist)      # registered last so every API route wins
    return app
