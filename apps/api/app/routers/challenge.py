"""Daily challenge: one word per UTC day, attempts scored by the server, ranked on a public leaderboard."""
from datetime import date, datetime, time, timedelta, timezone

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy import and_, func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.classes import models_dir
from app.db import get_db
from app.deps import get_current_user, get_current_user_optional, write_guard
from app.errors import ApiError
from app.inference import Scorer
from app.models import ChallengeAttempt, DailyChallenge, User
from app.schemas import (AttemptIn, AttemptOut, AttemptSummary, ChallengeDay, ChallengeStats, LeaderboardEntry, LeaderboardOut,
                         MyDay, Streak, TimelineStep, TodayOut)
from app.services.daily import pick_target
from app.services.drawings import enforce_limits, ink_length, normalise
from app.services.scoring import looks_automated, score_timeline
from app.services.stats import streaks

router = APIRouter(prefix="/challenge", tags=["challenge"])


def _now(request: Request) -> datetime:
    return request.app.state.clock()


def get_scorer(request: Request) -> Scorer:
    """The model is loaded on first use and then shared by every request."""
    state = request.app.state
    if state.scorer is None:
        with state.scorer_lock:
            if state.scorer is None:
                s = state.settings
                folder = models_dir(s)
                if folder is None or not (folder / s.model_version / "sketch.onnx").is_file():
                    raise ApiError(503, "model_unavailable", "The scoring model is not available on this server.")
                state.scorer = Scorer(folder, s.model_version, s.ml_root)
    return state.scorer


def _ensure_day(db: Session, request: Request, day: date) -> DailyChallenge:
    """Today's word, created on first request and frozen afterwards."""
    row = db.get(DailyChallenge, day)
    if row:
        return row
    scorer = get_scorer(request)
    previous = db.scalar(select(DailyChallenge.target).where(DailyChallenge.day == day - timedelta(days=1)))
    row = DailyChallenge(day=day, target=pick_target(scorer.classes, day, request.app.state.settings.secret_key, previous),
                         model_version=scorer.version)
    db.add(row)
    try:
        db.commit()
    except IntegrityError:                       # another request created the same day first: use theirs
        db.rollback()
        row = db.get(DailyChallenge, day)
    return row


def _my_attempts(db: Session, user_id: int, day: date) -> list[ChallengeAttempt]:
    return list(db.scalars(select(ChallengeAttempt).where(ChallengeAttempt.user_id == user_id, ChallengeAttempt.day == day)
                           .order_by(ChallengeAttempt.attempt_no)))


def _best_per_user(day: date):
    """One row per player for the day: their best counted attempt (highest score, then earliest)."""
    A = ChallengeAttempt
    rn = func.row_number().over(partition_by=A.user_id, order_by=(A.score.desc(), A.created_at.asc(), A.id.asc())).label("rn")
    inner = (select(A.id.label("id"), A.user_id.label("user_id"), A.score.label("score"), A.recognised_at.label("recognised_at"),
                    A.created_at.label("created_at"), rn)
             .where(A.day == day, A.suspect.is_(False)).subquery())
    return select(inner).where(inner.c.rn == 1).subquery()


def _entry(rank: int, *, user_id: int, display_name: str, show: bool, score: int, recognised_at: float | None,
           viewer_id: int | None) -> LeaderboardEntry:
    """Players who switched off 'show on leaderboard' keep their rank but appear as Anonymous."""
    return LeaderboardEntry(rank=rank, name=display_name if show else "Anonymous", score=score, recognised_at=recognised_at,
                            is_me=user_id == viewer_id)


def _standing(db: Session, day: date, user: User | None, limit: int):
    """(participants, top entries, the viewer's own entry or None)."""
    best = _best_per_user(day)
    participants = db.scalar(select(func.count()).select_from(best)) or 0
    rows = db.execute(
        select(best.c.id, best.c.user_id, best.c.score, best.c.recognised_at, User.display_name, User.show_on_leaderboard)
        .join(User, User.id == best.c.user_id)
        .order_by(best.c.score.desc(), best.c.created_at.asc(), best.c.id.asc()).limit(limit)
    ).all()
    viewer = user.id if user else None
    entries = [_entry(i + 1, user_id=r.user_id, display_name=r.display_name, show=r.show_on_leaderboard, score=r.score,
                      recognised_at=r.recognised_at, viewer_id=viewer) for i, r in enumerate(rows)]
    me = next((e for e in entries if e.is_me), None)
    if user is not None and me is None:
        mine = db.execute(select(best.c.id, best.c.score, best.c.recognised_at, best.c.created_at, best.c.user_id)
                          .where(best.c.user_id == user.id)).first()
        if mine:
            ahead = db.scalar(select(func.count()).select_from(best).where(or_(
                best.c.score > mine.score,
                and_(best.c.score == mine.score, or_(best.c.created_at < mine.created_at,
                                                     and_(best.c.created_at == mine.created_at, best.c.id < mine.id)))))) or 0
            me = _entry(ahead + 1, user_id=user.id, display_name=user.display_name, show=user.show_on_leaderboard,
                        score=mine.score, recognised_at=mine.recognised_at, viewer_id=user.id)
    return participants, entries, me


@router.get("/today", response_model=TodayOut)
def today(request: Request, user: User | None = Depends(get_current_user_optional), db: Session = Depends(get_db)):
    now = _now(request)
    challenge = _ensure_day(db, request, now.date())
    midnight = datetime.combine(now.date() + timedelta(days=1), time.min, tzinfo=timezone.utc)
    me = None
    if user is not None:
        attempts = _my_attempts(db, user.id, challenge.day)
        counted = [a.score for a in attempts if not a.suspect]
        me = MyDay(attempts_used=len(attempts), best_score=max(counted) if counted else None,
                   attempts=[AttemptSummary(attempt_no=a.attempt_no, score=a.score, recognised_at=a.recognised_at, counted=not a.suspect,
                                            created_at=a.created_at) for a in attempts])
    return TodayOut(day=challenge.day, target=challenge.target, model_version=challenge.model_version,
                    attempts_max=request.app.state.settings.attempts_per_day, seconds_left=int((midnight - now).total_seconds()), me=me)


@router.post("/attempts", response_model=AttemptOut)
def submit_attempt(body: AttemptIn, request: Request, user: User = Depends(write_guard), db: Session = Depends(get_db)):
    settings = request.app.state.settings
    enforce_limits(body.strokes, settings)
    challenge = _ensure_day(db, request, _now(request).date())
    used = db.scalar(select(func.count(ChallengeAttempt.id)).where(ChallengeAttempt.user_id == user.id, ChallengeAttempt.day == challenge.day)) or 0
    if used >= settings.attempts_per_day:
        raise ApiError(409, "attempts_exhausted", f"You have used all {settings.attempts_per_day} attempts for today. A new word arrives at midnight UTC.")

    strokes = normalise(body.strokes)
    timeline = get_scorer(request).timeline(strokes, challenge.target)       # the heavy part: 20 model runs on this drawing
    score, hit = score_timeline(timeline, challenge.target)
    final = timeline[-1]
    ink = ink_length(strokes)
    suspect = looks_automated(ink, body.duration_ms, settings.min_attempt_ms, settings.max_ink_per_ms)

    attempt = ChallengeAttempt(
        user_id=user.id, day=challenge.day, attempt_no=used + 1, score=score,
        recognised_at=hit.fraction if hit else None, confidence_at_hit=hit.top1_p if hit else None,
        final_guess=final.top1, final_confidence=final.top1_p, suspect=suspect,
        strokes=strokes, n_strokes=len(strokes), ink=ink, duration_ms=body.duration_ms,
    )
    db.add(attempt)
    try:
        db.commit()
    except IntegrityError:                                                    # two submissions raced for the same attempt number
        db.rollback()
        raise ApiError(409, "attempts_exhausted", "That attempt was already submitted. Reload to see your attempts.")

    mine = [a for a in _my_attempts(db, user.id, challenge.day) if not a.suspect]
    participants, _, me = _standing(db, challenge.day, user, limit=1)
    return AttemptOut(
        attempt_no=attempt.attempt_no, attempts_left=settings.attempts_per_day - attempt.attempt_no, score=score,
        recognised_at=attempt.recognised_at, confidence_at_hit=attempt.confidence_at_hit,
        final_guess=final.top1, final_confidence=final.top1_p, counted=not suspect,
        best_score=max((a.score for a in mine), default=None), rank=me.rank if me else None, participants=participants,
        timeline=[TimelineStep(fraction=s.fraction, top1=s.top1, top1_p=s.top1_p, p_target=s.p_target) for s in timeline],
    )


@router.get("/leaderboard", response_model=LeaderboardOut)
def leaderboard(request: Request, day: date | None = Query(None), limit: int = Query(20, ge=1, le=100),
                user: User | None = Depends(get_current_user_optional), db: Session = Depends(get_db)):
    current = _now(request).date()
    day = day or current
    if day > current:
        raise ApiError(422, "future_day", "There is no leaderboard for a day that has not happened yet.")
    challenge = _ensure_day(db, request, day) if day == current else db.get(DailyChallenge, day)
    if challenge is None:
        raise ApiError(404, "not_found", "There was no challenge on that day.")
    participants, entries, me = _standing(db, day, user, limit)
    return LeaderboardOut(day=day, target=challenge.target, participants=participants, entries=entries, me=me)


@router.get("/me", response_model=ChallengeStats)
def my_challenge_stats(request: Request, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    A = ChallengeAttempt
    rows = db.execute(select(A.day, func.max(A.score)).where(A.user_id == user.id, A.suspect.is_(False)).group_by(A.day).order_by(A.day.desc())).all()
    today_ = _now(request).date()
    current, longest = streaks({r[0] for r in rows}, today_)
    targets = dict(db.execute(select(DailyChallenge.day, DailyChallenge.target).where(DailyChallenge.day.in_([r[0] for r in rows[:30]]))).all())
    bests = [r[1] for r in rows]
    return ChallengeStats(
        played=len(rows), best_score=max(bests) if bests else None,
        average_best=round(sum(bests) / len(bests), 1) if bests else None,
        streak=Streak(current=current, longest=longest),
        history=[ChallengeDay(day=d, target=targets.get(d, "?"), best_score=s) for d, s in rows[:30]],
    )
