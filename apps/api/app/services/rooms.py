"""Classroom rules: round timing, results, totals and the state snapshot every client receives.

Timing is derived from stored timestamps and the app clock, never from a background job's say-so, so the state is the same whether a
timer fired or not. A round is
  drawing     until ends_at (or until the teacher ends it),
  collecting  for a short grace period so last-second drawings still arrive,
  results     afterwards: scores are revealed and the next round may start.
"""
import secrets
import statistics
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import Settings
from app.models import Room, RoomMember, RoomRound, RoundSubmission
from app.schemas_rooms import (AiSummary, MemberInfo, ResultEntry, RoomInfo, RoomState, RoundInfo, RoundResults, TotalEntry)

CODE_ALPHABET = "ABCDEFGHJKMNPQRSTUVWXYZ23456789"        # no 0/O/1/I/L: codes get read aloud and typed from a whiteboard
CODE_LENGTH = 6


def new_code() -> str:
    return "".join(secrets.choice(CODE_ALPHABET) for _ in range(CODE_LENGTH))


@dataclass(frozen=True)
class Viewer:
    role: str                       # "teacher" | "student"
    member: RoomMember | None = None


def aware(dt: datetime) -> datetime:
    """SQLite hands datetimes back without a zone; everything is stored as UTC, so put it back."""
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def effective_end(rnd: RoomRound) -> datetime:
    return aware(rnd.ended_at or rnd.ends_at)


def round_phase(rnd: RoomRound | None, now: datetime, settings: Settings) -> str:
    if rnd is None:
        return "lobby"
    end = effective_end(rnd)
    if now < end:
        return "drawing"
    return "collecting" if now < end + timedelta(seconds=settings.round_grace_s) else "results"


def latest_round(db: Session, room_id: int) -> RoomRound | None:
    return db.scalar(select(RoomRound).where(RoomRound.room_id == room_id).order_by(RoomRound.no.desc()).limit(1))


def _results(db: Session, rnd: RoomRound, viewer: Viewer) -> RoundResults:
    rows = db.execute(select(RoundSubmission, RoomMember.nickname).join(RoomMember, RoomMember.id == RoundSubmission.member_id)
                      .where(RoundSubmission.round_id == rnd.id)).all()
    # best first; ties go to whoever submitted first. Flagged drawings are listed but not ranked.
    ordered = sorted(rows, key=lambda r: (r[0].suspect, -r[0].score, r[0].created_at, r[0].id))
    entries, rank = [], 0
    for sub, nick in ordered:
        if not sub.suspect:
            rank += 1
        entries.append(ResultEntry(rank=None if sub.suspect else rank, submission_id=sub.id, nickname=nick, score=sub.score,
                                   recognised_at=sub.recognised_at, final_guess=sub.final_guess, counted=not sub.suspect,
                                   is_me=viewer.member is not None and sub.member_id == viewer.member.id))
    hits = [s.recognised_at for s, _ in rows if s.recognised_at is not None]
    ai = AiSummary(drawings=len(rows), named=len(hits), median_recognised_at=statistics.median(hits) if hits else None)
    return RoundResults(round_no=rnd.no, target=rnd.target, entries=entries, ai=ai)


def _totals(db: Session, room: Room, finished_ids: list[int], viewer: Viewer) -> list[TotalEntry]:
    points: dict[int, int] = {}
    played: dict[int, int] = {}
    if finished_ids:
        for sub in db.scalars(select(RoundSubmission).where(RoundSubmission.round_id.in_(finished_ids), RoundSubmission.suspect.is_(False))):
            points[sub.member_id] = points.get(sub.member_id, 0) + sub.score
            played[sub.member_id] = played.get(sub.member_id, 0) + 1
    members = [m for m in room.members if m.id in played]
    members.sort(key=lambda m: (-points[m.id], m.joined_at, m.id))
    return [TotalEntry(rank=i + 1, nickname=m.nickname, points=points[m.id], rounds_played=played[m.id],
                       is_me=viewer.member is not None and m.id == viewer.member.id) for i, m in enumerate(members)]


def build_state(db: Session, room: Room, viewer: Viewer, now: datetime, settings: Settings, online: set[int]) -> RoomState:
    """Everything one client needs to draw the room screen. Pushed over the WebSocket on every change and served by GET /state."""
    rounds = list(db.scalars(select(RoomRound).where(RoomRound.room_id == room.id).order_by(RoomRound.no)))
    current = rounds[-1] if rounds else None
    phase = round_phase(current, now, settings)
    finished = [r for r in rounds if round_phase(r, now, settings) == "results"]
    submitted_ids = set(db.scalars(select(RoundSubmission.member_id).where(RoundSubmission.round_id == current.id))) if current else set()

    def info(m: RoomMember) -> MemberInfo:
        return MemberInfo(nickname=m.nickname, online=m.id in online, submitted=m.id in submitted_ids,
                          is_me=viewer.member is not None and m.id == viewer.member.id)

    members = sorted(room.members, key=lambda m: (m.joined_at, m.id))
    shown_phase = "closed" if room.closed_at and phase in ("lobby", "results") else phase
    return RoomState(
        role=viewer.role, room=RoomInfo(id=room.id, name=room.name, code=room.code, closed=room.closed_at is not None),
        phase=shown_phase,
        round=RoundInfo(no=current.no, target=current.target, duration_s=current.duration_s,
                        seconds_left=max(0.0, (effective_end(current) - now).total_seconds())) if current and phase != "lobby" else None,
        me=info(viewer.member) if viewer.member else None, members=[info(m) for m in members],
        results=_results(db, current, viewer) if current and phase == "results" else None,
        totals=_totals(db, room, [r.id for r in finished], viewer), rounds_finished=len(finished),
    )


def deadlines(rnd: RoomRound, now: datetime, settings: Settings) -> list[float]:
    """Seconds from now until the round leaves 'drawing' and until it reaches 'results' (the moments clients need a push)."""
    end = effective_end(rnd)
    grace = timedelta(seconds=settings.round_grace_s)
    return [max(0.0, (t - now).total_seconds()) + 0.05 for t in (end, end + grace)]
