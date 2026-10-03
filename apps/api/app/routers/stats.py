"""Personal statistics from the signed-in user's own saved drawings."""
from datetime import datetime, timezone

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_db
from app.deps import get_current_user
from app.models import Drawing, User
from app.schemas import StatsOut
from app.services.stats import Facts, compute_stats

router = APIRouter(prefix="/me", tags=["account"])


@router.get("/stats", response_model=StatsOut)
def my_stats(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    rows = db.execute(select(Drawing.created_at, Drawing.label, Drawing.ai_guess, Drawing.recognised_at).where(Drawing.user_id == user.id, Drawing.mode != "teach"))
    return compute_stats([Facts(*r) for r in rows], datetime.now(timezone.utc).date())
