"""Pure helpers for submitted drawings: normalisation, derived fields and limits."""
import math

from app.config import Settings
from app.errors import ApiError

Stroke = list[tuple[float, float]]


def normalise(strokes: list[Stroke]) -> list[list[list[float]]]:
    """Round to 0.1 px (plenty for a 256-px frame) so stored drawings stay small."""
    return [[[round(x, 1), round(y, 1)] for x, y in s] for s in strokes]


def ink_length(strokes: list[list[list[float]]]) -> float:
    total = 0.0
    for s in strokes:
        for (x0, y0), (x1, y1) in zip(s, s[1:]):
            total += math.hypot(x1 - x0, y1 - y0)
    return round(total, 1)


def enforce_limits(strokes: list[Stroke], settings: Settings) -> None:
    points = sum(len(s) for s in strokes)
    if len(strokes) > settings.max_strokes or points > settings.max_points:
        raise ApiError(422, "too_complex", f"A drawing can have at most {settings.max_strokes} strokes and {settings.max_points} points.",
                       {"strokes": len(strokes), "points": points})
