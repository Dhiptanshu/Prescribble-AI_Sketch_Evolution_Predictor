"""Daily-challenge scoring rules (pure functions; the model itself lives in app/inference.py).

The drawing is revealed to the model in 20 steps of 5% of its ink. The AI "recognises" it at the first step where its #1 guess is the
target with at least 50% confidence. The earlier that happens, the higher the score: 100 at 5% of the ink down to 5 at 100%, and 0 if
the AI never gets there.
"""
from dataclasses import dataclass

FRACTIONS = tuple(i / 20 for i in range(1, 21))
HIT_CONFIDENCE = 0.5
STEP_POINTS = 5


@dataclass(frozen=True)
class Step:
    fraction: float
    top1: str
    top1_p: float
    p_target: float


def first_hit(timeline: list[Step], target: str) -> Step | None:
    for step in timeline:
        if step.top1 == target and step.top1_p >= HIT_CONFIDENCE:
            return step
    return None


def score_timeline(timeline: list[Step], target: str) -> tuple[int, Step | None]:
    hit = first_hit(timeline, target)
    if hit is None:
        return 0, None
    return (len(FRACTIONS) - FRACTIONS.index(hit.fraction)) * STEP_POINTS, hit


def looks_automated(ink: float, duration_ms: int | None, min_ms: int, max_ink_per_ms: float) -> bool:
    """Best-effort plausibility check on the reported drawing time. It cannot stop a determined cheat; it keeps instant,
    scripted submissions off the leaderboard (they are stored, flagged and reviewable)."""
    if duration_ms is None or duration_ms < min_ms:
        return True
    return ink / duration_ms > max_ink_per_ms
