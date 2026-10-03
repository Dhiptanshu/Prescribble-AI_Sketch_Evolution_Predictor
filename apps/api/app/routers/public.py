"""Read-only pages for shared drawings. No sign-in; exposes only what a share link is meant to show."""
from fastapi import APIRouter, Depends, Path, Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_db
from app.errors import ApiError
from app.models import Drawing
from app.ratelimit import public_rate_limit
from app.schemas import PublicDrawingOut

router = APIRouter(prefix="/public", tags=["public"], dependencies=[Depends(public_rate_limit)])


@router.get("/drawings/{token}", response_model=PublicDrawingOut)
def shared_drawing(response: Response, token: str = Path(min_length=8, max_length=32, pattern=r"^[A-Za-z0-9_-]+$"),
                   db: Session = Depends(get_db)):
    d = db.scalar(select(Drawing).where(Drawing.share_token == token))
    if d is None:
        raise ApiError(404, "not_found", "This drawing is not shared (or the link was turned off).")
    response.headers["Cache-Control"] = "no-cache"           # an unshared link must stop working immediately
    return PublicDrawingOut(
        strokes=d.strokes, label=d.label, ai_guess=d.ai_guess, ai_confidence=d.ai_confidence, recognised_at=d.recognised_at,
        created_at=d.created_at, model_version=d.model_version, author=d.user.display_name,
    )
