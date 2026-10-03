"""FastAPI application factory."""
import logging
import time
import uuid
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware

from app import models as _models  # noqa: F401  (registers the tables on Base.metadata)
from app.config import Settings, get_settings
from app.db import Base, make_engine, make_session_factory
from app.errors import install_error_handlers
from app.ratelimit import SlidingWindowLimiter
from app.routers import auth, health

API_PREFIX = "/api/v1"
log = logging.getLogger("prescribble.access")


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    engine = make_engine(settings.database_url)

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        yield
        engine.dispose()

    app = FastAPI(title=settings.app_name, version="0.1.0", lifespan=lifespan,
                  docs_url="/api/docs", openapi_url="/api/openapi.json", redoc_url=None)
    app.state.settings = settings
    app.state.engine = engine
    app.state.session_factory = make_session_factory(engine)
    app.state.auth_limiter = SlidingWindowLimiter(settings.auth_attempts_per_minute)

    if settings.env == "test":
        Base.metadata.create_all(engine)
    elif settings.auto_migrate:
        from app.migrations import run_migrations
        run_migrations(settings.database_url)

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

    install_error_handlers(app)
    app.include_router(health.router)
    app.include_router(auth.router, prefix=API_PREFIX)
    app.include_router(auth.me_router, prefix=API_PREFIX)
    if settings.web_dist:
        from app.web import install_web
        install_web(app, settings.web_dist)      # registered last so every API route wins
    return app
