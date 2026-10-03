"""Shared FastAPI dependencies."""
from fastapi import Depends, Request
from sqlalchemy.orm import Session

from app.db import get_db
from app.errors import ApiError
from app.models import User
from app.security import decode_session_token


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
