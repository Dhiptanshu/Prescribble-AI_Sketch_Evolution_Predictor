"""Personal statistics, computed from the user's own saved drawings (nothing is estimated or filled in)."""
from collections import defaultdict
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone

ACTIVITY_DAYS = 30
EARLY = 0.3     # "recognised early" = the AI had it by 30% of the ink


@dataclass(frozen=True)
class Facts:
    created_at: datetime
    label: str | None
    ai_guess: str
    recognised_at: float | None


def _day(dt: datetime) -> date:
    return (dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)).astimezone(timezone.utc).date()


def streaks(days: set[date], today: date) -> tuple[int, int]:
    """(current, longest). The current streak is still alive if the last drawing was today or yesterday."""
    if not days:
        return 0, 0
    longest = run = 0
    prev: date | None = None
    for d in sorted(days):
        run = run + 1 if prev and d - prev == timedelta(days=1) else 1
        longest = max(longest, run)
        prev = d
    cursor = today if today in days else today - timedelta(days=1)
    current = 0
    while cursor in days:
        current += 1
        cursor -= timedelta(days=1)
    return current, longest


def compute_stats(facts: list[Facts], today: date) -> dict:
    labelled = [f for f in facts if f.label]
    recognised = [f.recognised_at for f in labelled if f.recognised_at is not None]
    per_class: dict[str, list[Facts]] = defaultdict(list)
    for f in labelled:
        per_class[f.label].append(f)  # type: ignore[index]

    by_class = []
    for label, items in per_class.items():
        fr = [i.recognised_at for i in items if i.recognised_at is not None]
        by_class.append({"label": label, "count": len(items), "avg_recognised_at": round(sum(fr) / len(fr), 3) if fr else None})
    by_class.sort(key=lambda c: (-c["count"], c["label"]))

    counts: dict[date, int] = defaultdict(int)
    for f in facts:
        counts[_day(f.created_at)] += 1
    current, longest = streaks(set(counts), today)
    activity = [{"date": (today - timedelta(days=i)).isoformat(), "count": counts.get(today - timedelta(days=i), 0)}
                for i in range(ACTIVITY_DAYS - 1, -1, -1)]

    created = sorted(f.created_at for f in facts)
    return {
        "total": len(facts),
        "labelled": len(labelled),
        "ai_final_correct": sum(1 for f in labelled if f.ai_guess == f.label),
        "ai_ever_recognised": len(recognised),
        "avg_recognised_at": round(sum(recognised) / len(recognised), 3) if recognised else None,
        "early_rate": round(sum(1 for r in recognised if r <= EARLY) / len(labelled), 3) if labelled else None,
        "by_class": by_class,
        "streak": {"current": current, "longest": longest},
        "activity": activity,
        "first_drawing_at": created[0] if created else None,
        "last_drawing_at": created[-1] if created else None,
    }
