"""Per-key usage counters, kept in the database so they survive restarts and are shared by every replica."""
from datetime import date, timedelta

from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models import ApiUsage


def used_on(db: Session, key_id: int, day: date) -> int:
    return db.scalar(select(ApiUsage.requests).where(ApiUsage.key_id == key_id, ApiUsage.day == day)) or 0


def record(db: Session, key_id: int, day: date, ok: bool, ms: float) -> None:
    """Count one request. Updates the day's row in place; creates it on the first request of the day."""
    def bump() -> int:
        return db.execute(update(ApiUsage).where(ApiUsage.key_id == key_id, ApiUsage.day == day).values(
            requests=ApiUsage.requests + 1, errors=ApiUsage.errors + (0 if ok else 1), total_ms=ApiUsage.total_ms + ms)).rowcount

    if bump() == 0:
        db.add(ApiUsage(key_id=key_id, day=day, requests=1, errors=0 if ok else 1, total_ms=ms))
        try:
            db.flush()
        except IntegrityError:                  # a concurrent request created today's row first
            db.rollback()
            bump()
    db.commit()


def daily_series(db: Session, key_ids: list[int], today: date, days: int) -> list[dict]:
    """Zero-filled per-day totals for the given keys, oldest first."""
    since = today - timedelta(days=days - 1)
    rows = db.execute(select(ApiUsage.day, ApiUsage.requests, ApiUsage.errors, ApiUsage.total_ms)
                      .where(ApiUsage.key_id.in_(key_ids), ApiUsage.day >= since)).all() if key_ids else []
    by_day: dict[date, list[float]] = {}
    for day, requests, errors, total_ms in rows:
        agg = by_day.setdefault(day, [0, 0, 0.0])
        agg[0] += requests; agg[1] += errors; agg[2] += total_ms
    out = []
    for i in range(days):
        d = since + timedelta(days=i)
        requests, errors, total_ms = by_day.get(d, [0, 0, 0.0])
        out.append({"day": d, "requests": int(requests), "errors": int(errors), "avg_ms": round(total_ms / requests, 2) if requests else None})
    return out
