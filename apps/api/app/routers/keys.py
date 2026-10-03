"""API key management for signed-in users. The full key is returned exactly once, when it is created."""
from datetime import datetime

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db import get_db
from app.deps import get_current_user, write_guard
from app.errors import ApiError
from app.models import ApiKey, ApiUsage, User
from app.schemas import KeyCreate, KeyCreated, KeyOut, UsageDay
from app.services.apikeys import generate_key
from app.services.metering import daily_series

router = APIRouter(prefix="/keys", tags=["api keys"])


def _own(db: Session, user: User, key_id: int) -> ApiKey:
    key = db.scalar(select(ApiKey).where(ApiKey.id == key_id, ApiKey.user_id == user.id))
    if key is None:
        raise ApiError(404, "not_found", "API key not found.")          # 404 for other people's keys, so ids cannot be probed
    return key


@router.post("", response_model=KeyCreated, status_code=201)
def create_key(body: KeyCreate, request: Request, user: User = Depends(write_guard), db: Session = Depends(get_db)):
    settings = request.app.state.settings
    active = db.scalar(select(func.count(ApiKey.id)).where(ApiKey.user_id == user.id, ApiKey.revoked_at.is_(None))) or 0
    if active >= settings.max_keys_per_user:
        raise ApiError(409, "key_limit", f"You can have up to {settings.max_keys_per_user} active API keys. Revoke one to create another.")
    full, prefix, digest = generate_key()
    row = ApiKey(user_id=user.id, name=body.name, prefix=prefix, key_hash=digest, daily_limit=settings.api_daily_limit)
    db.add(row)
    db.commit()
    return KeyCreated(**KeyOut.model_validate(row).model_dump(), key=full)


@router.get("", response_model=list[KeyOut])
def list_keys(request: Request, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    today = request.app.state.clock().date()
    keys = list(db.scalars(select(ApiKey).where(ApiKey.user_id == user.id).order_by(ApiKey.id.desc())))
    used = dict(db.execute(select(ApiUsage.key_id, ApiUsage.requests).where(ApiUsage.day == today, ApiUsage.key_id.in_([k.id for k in keys]))).all()) if keys else {}
    return [KeyOut.model_validate(k).model_copy(update={"used_today": used.get(k.id, 0)}) for k in keys]


@router.delete("/{key_id}", status_code=204)
def revoke_key(key_id: int, request: Request, user: User = Depends(write_guard), db: Session = Depends(get_db)):
    key = _own(db, user, key_id)
    if key.revoked_at is None:
        key.revoked_at = request.app.state.clock()
        db.commit()


@router.get("/{key_id}/usage", response_model=list[UsageDay])
def key_usage(key_id: int, request: Request, days: int = Query(14, ge=1, le=90), user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    key = _own(db, user, key_id)
    return daily_series(db, [key.id], request.app.state.clock().date(), days)
