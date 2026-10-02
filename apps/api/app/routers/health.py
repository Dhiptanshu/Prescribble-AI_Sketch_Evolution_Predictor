"""Liveness / readiness."""
from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.db import get_db
from app.errors import ApiError

router = APIRouter(tags=["ops"])


@router.get("/healthz")
def healthz(db: Session = Depends(get_db)):
    try:
        db.execute(text("SELECT 1"))
    except Exception as exc:  # noqa: BLE001
        raise ApiError(503, "db_unavailable", "Database is not reachable.") from exc
    return {"status": "ok"}
