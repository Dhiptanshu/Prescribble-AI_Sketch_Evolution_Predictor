"""Teach the AI: people who opted in draw words the model needs more examples of. Contributions are ordinary saved drawings (mode "teach")
that are never shown in the gallery or the personal stats, only counted here, and removable in one call."""
from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app.classes import known_classes
from app.db import get_db
from app.deps import get_current_user, write_guard
from app.errors import ApiError
from app.models import Drawing, User
from app.schemas import TeachNext, TeachSummary
from app.services import training_data
from app.services.registry import active_version

router = APIRouter(prefix="/teach", tags=["teach"])


def _classes(request: Request) -> frozenset[str]:
    settings = request.app.state.settings
    classes = known_classes(settings, active_version(settings))
    if not classes:
        raise ApiError(503, "model_unavailable", "The model's class list is not available on this server.")
    return classes


def _mine(db: Session, user: User) -> int:
    return db.scalar(select(func.count(Drawing.id)).where(Drawing.user_id == user.id, Drawing.mode == "teach")) or 0


def _summary(request: Request, db: Session, user: User) -> TeachSummary:
    s = training_data.summary(db, _classes(request))
    return TeachSummary(mine=_mine(db, user), ready_total=s["ready"], classes_covered=s["classes_covered"], classes_total=s["classes_total"],
                        consent=user.consent_training, model_version=active_version(request.app.state.settings))


@router.get("/summary", response_model=TeachSummary)
def summary(request: Request, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return _summary(request, db, user)


@router.get("/next", response_model=TeachNext)
def next_word(request: Request, avoid: str | None = Query(None, max_length=40), user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """The word the model has the fewest examples of (never `avoid`, the word just drawn)."""
    if not user.consent_training:
        raise ApiError(409, "consent_required", "Turn on training consent in Settings first: your teaching drawings are used to train the model.")
    return TeachNext(target=training_data.next_target(db, _classes(request), avoid), summary=_summary(request, db, user))


@router.delete("/contributions")
def withdraw(user: User = Depends(write_guard), db: Session = Depends(get_db)):
    """Delete every drawing this person contributed through the Teach page."""
    result = db.execute(delete(Drawing).where(Drawing.user_id == user.id, Drawing.mode == "teach"))
    db.commit()
    return {"deleted": result.rowcount}
