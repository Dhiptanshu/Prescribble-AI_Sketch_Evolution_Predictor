"""Saved drawings: create, list, read, relabel, delete and share. Every route is scoped to the signed-in owner."""
import secrets

from fastapi import APIRouter, Depends, Query, Request, Response
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.classes import known_classes
from app.db import get_db
from app.deps import get_current_user, write_guard
from app.errors import ApiError
from app.models import Drawing, User
from app.schemas import DrawingCreate, DrawingOut, DrawingPage, DrawingPatch, ShareOut
from app.services.drawings import enforce_limits, ink_length, normalise

router = APIRouter(prefix="/drawings", tags=["drawings"])


def _own(db: Session, user: User, drawing_id: int) -> Drawing:
    """404 (never 403) for someone else's drawing, so ids cannot be probed."""
    d = db.scalar(select(Drawing).where(Drawing.id == drawing_id, Drawing.user_id == user.id))
    if d is None:
        raise ApiError(404, "not_found", "Drawing not found.")
    return d


def _check_class(request: Request, version: str, name: str | None, field: str) -> None:
    known = known_classes(request.app.state.settings, version)
    if name is not None and known is not None and name not in known:
        raise ApiError(422, "unknown_class", f"'{name}' is not a class of model {version}.", [{"field": field, "message": "unknown class"}])


@router.post("", response_model=DrawingOut, status_code=201)
def create(body: DrawingCreate, request: Request, user: User = Depends(write_guard), db: Session = Depends(get_db)):
    settings = request.app.state.settings
    enforce_limits(body.strokes, settings)
    _check_class(request, body.model_version, body.label, "label")
    _check_class(request, body.model_version, body.ai_guess, "ai_guess")
    if body.recognised_at is not None and not body.label:
        raise ApiError(422, "validation_error", "recognised_at needs a label.", [{"field": "recognised_at", "message": "requires a label"}])
    teach = body.mode == "teach"
    if teach and not (body.label and user.consent_training):
        raise ApiError(409, "consent_required", "Teaching the AI needs training consent (turn it on in Settings) and a word to draw.")
    mine = db.scalar(select(func.count(Drawing.id)).where(Drawing.user_id == user.id, (Drawing.mode == "teach") if teach else (Drawing.mode != "teach")))
    cap = settings.max_teach_per_user if teach else settings.max_drawings_per_user
    if mine >= cap:
        what = "teaching contributions" if teach else "saved drawings"
        raise ApiError(409, "quota_exceeded", f"You can keep up to {cap} {what}. Delete some to add more.")
    strokes = normalise(body.strokes)
    drawing = Drawing(
        user_id=user.id, label=body.label, ai_guess=body.ai_guess, ai_confidence=body.ai_confidence, recognised_at=body.recognised_at,
        mode=body.mode, model_version=body.model_version, strokes=strokes, n_strokes=len(strokes), ink=ink_length(strokes),
        duration_ms=body.duration_ms, input_type=body.input_type,
        label_confirmed=bool(body.label) and (teach or body.label_confirmed),      # a teaching word is the task itself; otherwise the person must say so
    )
    db.add(drawing)
    db.commit()
    return drawing


@router.get("", response_model=DrawingPage)
def list_drawings(limit: int = Query(24, ge=1, le=50), before: int | None = Query(None, ge=1),
                  user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Newest first. Pass `next_before` from the previous page as `before` to continue."""
    q = select(Drawing).where(Drawing.user_id == user.id, Drawing.mode != "teach")      # teaching contributions live on the Teach page
    if before is not None:
        q = q.where(Drawing.id < before)
    rows = list(db.scalars(q.order_by(Drawing.id.desc()).limit(limit + 1)))
    page = rows[:limit]
    return {"items": page, "next_before": page[-1].id if len(rows) > limit else None}


@router.get("/{drawing_id}", response_model=DrawingOut)
def get_drawing(drawing_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return _own(db, user, drawing_id)


@router.patch("/{drawing_id}", response_model=DrawingOut)
def relabel(drawing_id: int, body: DrawingPatch, request: Request, user: User = Depends(write_guard), db: Session = Depends(get_db)):
    d = _own(db, user, drawing_id)
    _check_class(request, d.model_version, body.label, "label")
    d.label = body.label
    d.label_confirmed = body.label is not None          # choosing a label here is the person saying what they drew
    if body.label is None:
        d.recognised_at = None            # without a label there is nothing for the AI to have recognised
    db.commit()
    return d


@router.delete("/{drawing_id}", status_code=204)
def delete(drawing_id: int, user: User = Depends(write_guard), db: Session = Depends(get_db)):
    db.delete(_own(db, user, drawing_id))
    db.commit()


@router.post("/{drawing_id}/share", response_model=ShareOut)
def share(drawing_id: int, user: User = Depends(write_guard), db: Session = Depends(get_db)):
    """Make the drawing viewable by anyone with the link. Idempotent: re-sharing returns the same link."""
    d = _own(db, user, drawing_id)
    if not d.share_token:
        d.share_token = secrets.token_urlsafe(9)      # 72 bits: not guessable
        db.commit()
    return {"token": d.share_token}


@router.delete("/{drawing_id}/share", status_code=204)
def unshare(drawing_id: int, user: User = Depends(write_guard), db: Session = Depends(get_db)):
    d = _own(db, user, drawing_id)
    d.share_token = None
    db.commit()
    return Response(status_code=204)
