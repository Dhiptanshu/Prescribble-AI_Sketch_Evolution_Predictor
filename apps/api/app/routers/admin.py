"""Operator dashboard numbers. Admin only. Every figure is counted from the database; owners are shown by display name, never by email."""
from datetime import timedelta

from fastapi import APIRouter, Depends, Request
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db import get_db
from app.deps import require_admin
from app.models import ApiKey, ApiUsage, ChallengeAttempt, Drawing, User
from app.classes import known_classes
from app.schemas import AdminMetrics, ApiMetrics, ChallengeToday, CountPair, TopKey, TrainingMetrics
from app.services import training_data
from app.inference import reload_active
from app.services.metering import daily_series
from app.services.registry import active_version

router = APIRouter(prefix="/admin", tags=["admin"], dependencies=[Depends(require_admin)])


def _training(request: Request, db: Session) -> TrainingMetrics:
    s = training_data.summary(db, known_classes(request.app.state.settings, active_version(request.app.state.settings)))
    return TrainingMetrics(ready=s["ready"], classes_covered=s["classes_covered"], classes_total=s["classes_total"], contributors=s["contributors"],
                           by_input_type=s["by_input_type"])


@router.get("/metrics", response_model=AdminMetrics)
def metrics(request: Request, db: Session = Depends(get_db)):
    now = request.app.state.clock()
    today, week_ago = now.date(), now - timedelta(days=7)
    week_start = today - timedelta(days=6)

    def count(model, *where):
        return db.scalar(select(func.count()).select_from(model).where(*where)) or 0

    key_ids = list(db.scalars(select(ApiKey.id)))
    daily = daily_series(db, key_ids, today, 14)
    last7 = daily[-7:]
    requests_7d = sum(d["requests"] for d in last7)
    weighted_ms = sum((d["avg_ms"] or 0) * d["requests"] for d in last7)

    top = db.execute(
        select(ApiKey.prefix, ApiKey.name, User.display_name, func.sum(ApiUsage.requests).label("n"))
        .join(ApiUsage, ApiUsage.key_id == ApiKey.id).join(User, User.id == ApiKey.user_id)
        .where(ApiUsage.day >= week_start).group_by(ApiKey.id, User.id).order_by(func.sum(ApiUsage.requests).desc()).limit(5)
    ).all()

    return AdminMetrics(
        users=CountPair(total=count(User), last_7_days=count(User, User.created_at >= week_ago)),
        drawings=CountPair(total=count(Drawing), last_7_days=count(Drawing, Drawing.created_at >= week_ago)),
        challenge_today=ChallengeToday(
            players=db.scalar(select(func.count(func.distinct(ChallengeAttempt.user_id))).where(ChallengeAttempt.day == today)) or 0,
            attempts=count(ChallengeAttempt, ChallengeAttempt.day == today),
            flagged=count(ChallengeAttempt, ChallengeAttempt.day == today, ChallengeAttempt.suspect.is_(True)),
        ),
        api=ApiMetrics(
            active_keys=count(ApiKey, ApiKey.revoked_at.is_(None)),
            requests_today=daily[-1]["requests"], requests_7d=requests_7d, errors_7d=sum(d["errors"] for d in last7),
            avg_ms_7d=round(weighted_ms / requests_7d, 2) if requests_7d else None,
            daily=daily,
            top_keys=[TopKey(prefix=p, name=n, owner=o, requests_7d=int(r)) for p, n, o, r in top],
        ),
        model_version=active_version(request.app.state.settings),
        model_loaded=request.app.state.scorer is not None,
        training=_training(request, db),
    )


@router.post("/model/reload")
def reload_model(request: Request):
    """After `python -m src.flywheel.registry promote`: start answering with the newly live version, no restart needed.
    Days and rounds already in progress keep the model they started with."""
    return {"active": reload_active(request)}
