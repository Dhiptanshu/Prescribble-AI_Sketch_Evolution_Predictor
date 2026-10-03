"""Pick the word of the day: deterministic for a given secret, unpredictable without it, and never the same word two days in a row."""
import hashlib
import hmac
from datetime import date


def pick_target(classes: list[str], day: date, secret: str, previous: str | None) -> str:
    ordered = sorted(classes)                                  # stable order, independent of how the model lists its classes
    digest = hmac.new(secret.encode(), day.isoformat().encode(), hashlib.sha256).digest()
    index = int.from_bytes(digest[:8], "big") % len(ordered)
    if previous is not None and len(ordered) > 1 and ordered[index] == previous:
        index = (index + 1) % len(ordered)
    return ordered[index]


CHALLENGE_FRACTION = "0.5"           # "the model gets it by half the ink" is the bar a class must clear to be a fair challenge word
CHALLENGE_MIN_TOP1 = 0.5


def challenge_classes(meta: dict, minimum: float = CHALLENGE_MIN_TOP1) -> list[str]:
    """The classes worth setting as a challenge: those the model measurably recognises by half the ink on its own held-out sketches
    (per-class Top-1 in the model's results). A model with no per-class numbers (v1, v2) offers every class."""
    per_class = (meta.get("test_results", {}).get(CHALLENGE_FRACTION) or {}).get("per_class_top1")
    classes = meta["classes"]
    if not per_class:
        return list(classes)
    eligible = [c for c, acc in zip(classes, per_class) if acc is not None and acc >= minimum]
    return eligible or list(classes)
