"""Which saved drawings may be used to train a model, and how to hand them to the training pipeline.

A drawing is training-ready only when ALL of these hold:
  * its owner has training consent switched on right now (turning it off removes their drawings from every later export),
  * the label is set and the person confirmed it (an AI guess that was never checked is not a label),
  * the label is a class of the model being trained,
  * it is not an exact duplicate of another ready drawing.
Exports carry no account identity: the `uid` is a one-way hash of the drawing id, which also keeps each drawing on one side of the
train / held-out split between exports (src/flywheel/dataset.py).
"""
import hashlib
import secrets
from collections import Counter

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Drawing, User


def uid_of(drawing_id: int) -> str:
    return hashlib.sha256(f"prescribble-drawing:{drawing_id}".encode()).hexdigest()[:16]


def ready(db: Session, classes: frozenset[str] | None) -> list[Drawing]:
    """Training-ready drawings, oldest first, exact duplicates removed. `classes` None = class names cannot be checked here."""
    rows = db.scalars(
        select(Drawing).join(User, User.id == Drawing.user_id)
        .where(User.consent_training.is_(True), Drawing.label_confirmed.is_(True), Drawing.label.is_not(None)).order_by(Drawing.id)
    )
    seen: set[str] = set()
    out = []
    for d in rows:
        if classes is not None and d.label not in classes:
            continue
        key = hashlib.sha256(f"{d.label}:{d.strokes}".encode()).hexdigest()
        if key in seen:
            continue
        seen.add(key)
        out.append(d)
    return out


def summary(db: Session, classes: frozenset[str] | None) -> dict:
    rows = ready(db, classes)
    by_class = Counter(d.label for d in rows)
    consenting = len({d.user_id for d in rows})
    return {"ready": len(rows), "classes_covered": len(by_class), "classes_total": len(classes) if classes else None,
            "by_input_type": dict(Counter(d.input_type or "unknown" for d in rows)), "contributors": consenting,
            "by_class": dict(by_class)}


def next_target(db: Session, classes: frozenset[str], avoid: str | None = None) -> str:
    """The class with the fewest ready drawings (so contributions fill the gaps first), never `avoid` when there is a choice."""
    counts = Counter({c: 0 for c in classes})
    counts.update(d.label for d in ready(db, classes))
    options = [c for c in counts if c != avoid] or list(counts)
    fewest = min(counts[c] for c in options)
    return secrets.choice(sorted(c for c in options if counts[c] == fewest))


def export_records(db: Session, classes: frozenset[str] | None, model_version: str | None = None) -> list[dict]:
    return [
        {"uid": uid_of(d.id), "label": d.label, "strokes": d.strokes, "source": d.mode, "input_type": d.input_type or "unknown",
         "model_version": d.model_version, "created": d.created_at.isoformat()}
        for d in ready(db, classes)
    ]
