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
