"""Shared FastAPI dependencies."""
from datetime import datetime, time, timedelta, timezone

from fastapi import Depends, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_db
from app.errors import ApiError
from app.models import ApiKey, User
from app.security import decode_session_token
from app.services.apikeys import hash_key, looks_like_key
from app.services.metering import used_on


def _token_from(request: Request) -> str | None:
    settings = request.app.state.settings
    token = request.cookies.get(settings.cookie_name)
    if token:
        return token
    header = request.headers.get("authorization", "")
    return header[7:] if header.lower().startswith("bearer ") else None


def get_current_user_optional(request: Request, db: Session = Depends(get_db)) -> User | None:
    token = _token_from(request)
    if not token:
        return None
    user_id = decode_session_token(token, request.app.state.settings.secret_key)
    return db.get(User, user_id) if user_id is not None else None


def get_current_user(user: User | None = Depends(get_current_user_optional)) -> User:
    if user is None:
        raise ApiError(401, "unauthenticated", "Sign in to continue.")
    return user


def require_admin(user: User = Depends(get_current_user)) -> User:
    if not user.is_admin:
        raise ApiError(403, "forbidden", "Admin access required.")
    return user


def write_guard(request: Request, user: User = Depends(get_current_user)) -> User:
    """Signed-in user, limited to `writes_per_minute` mutating calls."""
    request.app.state.write_limiter.check(f"user:{user.id}")
    return user


def seconds_until_midnight_utc(now: datetime) -> int:
    midnight = datetime.combine(now.date() + timedelta(days=1), time.min, tzinfo=timezone.utc)
    return max(1, int((midnight - now).total_seconds()))


def _raw_api_key(request: Request) -> str:
    bearer = request.headers.get("authorization", "")
    return request.headers.get("x-api-key") or (bearer[7:] if bearer.lower().startswith("bearer ") else "")


def authenticate_key(request: Request, db: Session = Depends(get_db)) -> ApiKey:
    """Secret-key authentication for the REST API, plus its burst limit and daily quota.

    Secret keys are for servers. A browser always attaches an Origin header, so any request that carries one is refused: a key that
    ends up in front-end code cannot be abused from a web page. (Websites should embed the widget, which needs no key.)
    """
    if request.headers.get("origin"):
        raise ApiError(403, "browser_not_allowed", "API keys are secret and must not be used from a browser. Call the API from your server, "
                                                    "or embed the Prescribble widget on your web page.")
    raw = _raw_api_key(request)
    key = db.scalar(select(ApiKey).where(ApiKey.key_hash == hash_key(raw))) if looks_like_key(raw) else None
    if key is None or key.revoked_at is not None:
        raise ApiError(401, "invalid_api_key", "Missing, malformed or revoked API key. Send it as 'Authorization: Bearer <key>' or 'X-API-Key: <key>'.")
    request.app.state.api_limiter.check(f"key:{key.id}")
    now = request.app.state.clock()
    if used_on(db, key.id, now.date()) >= key.daily_limit:
        raise ApiError(429, "quota_exceeded", f"This key has used its {key.daily_limit} requests for today. The quota resets at midnight UTC.",
                       {"retry_after": seconds_until_midnight_utc(now)})
    return key
