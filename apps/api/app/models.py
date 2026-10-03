"""ORM models. Keep one class per table; relationships are added as features land."""
from datetime import date, datetime, timezone

from sqlalchemy import JSON, Boolean, Date, DateTime, Float, ForeignKey, Index, Integer, String, UniqueConstraint, false, true
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(254), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    display_name: Mapped[str] = mapped_column(String(40))
    is_admin: Mapped[bool] = mapped_column(Boolean, default=False)
    consent_training: Mapped[bool] = mapped_column(Boolean, default=False)   # opt-in only
    show_on_leaderboard: Mapped[bool] = mapped_column(Boolean, default=True, server_default=true())   # off = listed as "Anonymous"
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    drawings: Mapped[list["Drawing"]] = relationship(back_populates="user", cascade="all, delete-orphan", passive_deletes=True)
    attempts: Mapped[list["ChallengeAttempt"]] = relationship(back_populates="user", cascade="all, delete-orphan", passive_deletes=True)
    api_keys: Mapped[list["ApiKey"]] = relationship(back_populates="user", cascade="all, delete-orphan", passive_deletes=True)
    rooms: Mapped[list["Room"]] = relationship(cascade="all, delete-orphan", passive_deletes=True)


class Drawing(Base):
    """A saved drawing. Strokes are in the model's fixed 0..255 frame. Stored only when the user chooses to save."""

    __tablename__ = "drawings"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)

    label: Mapped[str | None] = mapped_column(String(40))            # what the user says they drew (a known class)
    ai_guess: Mapped[str] = mapped_column(String(40))                # the AI's final top-1 guess
    ai_confidence: Mapped[float] = mapped_column(Float)
    recognised_at: Mapped[float | None] = mapped_column(Float)       # fraction of the ink from which the AI's top-1 matched the label (client-reported)
    mode: Mapped[str] = mapped_column(String(16), default="free")    # free | challenge | teach (drawn on request to teach the AI)
    label_confirmed: Mapped[bool] = mapped_column(Boolean, default=False, server_default=false())   # the person checked the label (never just the AI's guess)
    input_type: Mapped[str | None] = mapped_column(String(8))        # pointer used for the first stroke: mouse | touch | pen (client-reported)
    model_version: Mapped[str] = mapped_column(String(16))

    strokes: Mapped[list] = mapped_column(JSON)                      # [[[x, y], ...], ...]
    n_strokes: Mapped[int] = mapped_column(Integer)                  # recomputed by the server, never trusted from the client
    ink: Mapped[float] = mapped_column(Float)
    duration_ms: Mapped[int | None] = mapped_column(Integer)

    share_token: Mapped[str | None] = mapped_column(String(32), unique=True, index=True)   # set while the drawing is publicly shared

    user: Mapped[User] = relationship(back_populates="drawings")


class DailyChallenge(Base):
    """The word of the day. Created on first request and then frozen, so history never changes."""

    __tablename__ = "daily_challenges"

    day: Mapped[date] = mapped_column(Date, primary_key=True)        # UTC date
    target: Mapped[str] = mapped_column(String(40))
    model_version: Mapped[str] = mapped_column(String(16))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class ChallengeAttempt(Base):
    """One scored attempt. The score is computed by the server from the strokes; nothing about it is client-supplied."""

    __tablename__ = "challenge_attempts"
    __table_args__ = (UniqueConstraint("user_id", "day", "attempt_no"), Index("ix_attempts_day_score", "day", "score"))

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    day: Mapped[date] = mapped_column(Date)
    attempt_no: Mapped[int] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    score: Mapped[int] = mapped_column(Integer)                       # 0 (never recognised) or 5..100 in steps of 5
    recognised_at: Mapped[float | None] = mapped_column(Float)        # fraction of the ink at which the AI first named the target
    confidence_at_hit: Mapped[float | None] = mapped_column(Float)
    final_guess: Mapped[str] = mapped_column(String(40))
    final_confidence: Mapped[float] = mapped_column(Float)
    suspect: Mapped[bool] = mapped_column(Boolean, default=False)     # kept for review, excluded from the leaderboard

    strokes: Mapped[list] = mapped_column(JSON)
    n_strokes: Mapped[int] = mapped_column(Integer)
    ink: Mapped[float] = mapped_column(Float)
    duration_ms: Mapped[int | None] = mapped_column(Integer)

    user: Mapped[User] = relationship(back_populates="attempts")


class ApiKey(Base):
    """A secret key for the REST API. Only a SHA-256 hash is stored; the key itself is shown once, at creation."""

    __tablename__ = "api_keys"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(60))
    prefix: Mapped[str] = mapped_column(String(16))                    # first characters, so people can tell their keys apart
    key_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    daily_limit: Mapped[int] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    user: Mapped[User] = relationship(back_populates="api_keys")
    usage: Mapped[list["ApiUsage"]] = relationship(cascade="all, delete-orphan", passive_deletes=True)


class ApiUsage(Base):
    """Request counters per key per UTC day (real metering: nothing is sampled or estimated)."""

    __tablename__ = "api_usage"
    __table_args__ = (UniqueConstraint("key_id", "day"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    key_id: Mapped[int] = mapped_column(ForeignKey("api_keys.id", ondelete="CASCADE"), index=True)
    day: Mapped[date] = mapped_column(Date)
    requests: Mapped[int] = mapped_column(Integer, default=0)
    errors: Mapped[int] = mapped_column(Integer, default=0)
    total_ms: Mapped[float] = mapped_column(Float, default=0.0)      # summed model time, so avg = total_ms / requests


class Room(Base):
    """A classroom: a teacher's room that students join with a short code and a nickname (no student account needed)."""

    __tablename__ = "rooms"

    id: Mapped[int] = mapped_column(primary_key=True)
    owner_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(60))
    code: Mapped[str] = mapped_column(String(8), unique=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))     # a closed room accepts no joins and no submissions

    members: Mapped[list["RoomMember"]] = relationship(cascade="all, delete-orphan", passive_deletes=True)
    rounds: Mapped[list["RoomRound"]] = relationship(cascade="all, delete-orphan", passive_deletes=True, order_by="RoomRound.no")


class RoomMember(Base):
    """A student in a room. Identified by a random token (only its hash is stored), which the browser keeps for the session."""

    __tablename__ = "room_members"
    __table_args__ = (UniqueConstraint("room_id", "nickname_key"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    room_id: Mapped[int] = mapped_column(ForeignKey("rooms.id", ondelete="CASCADE"), index=True)
    nickname: Mapped[str] = mapped_column(String(24))
    nickname_key: Mapped[str] = mapped_column(String(24))                  # lower-cased, so "Sam" and "sam" cannot both join
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    joined_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class RoomRound(Base):
    """One word, one timer. The round is 'drawing' until ends_at (or the teacher ends it), then students' last drawings are collected."""

    __tablename__ = "room_rounds"
    __table_args__ = (UniqueConstraint("room_id", "no"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    room_id: Mapped[int] = mapped_column(ForeignKey("rooms.id", ondelete="CASCADE"), index=True)
    no: Mapped[int] = mapped_column(Integer)
    target: Mapped[str] = mapped_column(String(40))
    model_version: Mapped[str] = mapped_column(String(16))
    duration_s: Mapped[int] = mapped_column(Integer)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    ends_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))      # set when the teacher ends the round early

    submissions: Mapped[list["RoundSubmission"]] = relationship(cascade="all, delete-orphan", passive_deletes=True)


class RoundSubmission(Base):
    """A student's drawing for a round, scored by the server exactly like a daily-challenge attempt."""

    __tablename__ = "round_submissions"
    __table_args__ = (UniqueConstraint("round_id", "member_id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    round_id: Mapped[int] = mapped_column(ForeignKey("room_rounds.id", ondelete="CASCADE"), index=True)
    member_id: Mapped[int] = mapped_column(ForeignKey("room_members.id", ondelete="CASCADE"), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    score: Mapped[int] = mapped_column(Integer)
    recognised_at: Mapped[float | None] = mapped_column(Float)
    final_guess: Mapped[str] = mapped_column(String(40))
    final_confidence: Mapped[float] = mapped_column(Float)
    suspect: Mapped[bool] = mapped_column(Boolean, default=False)

    strokes: Mapped[list] = mapped_column(JSON)
    n_strokes: Mapped[int] = mapped_column(Integer)
    ink: Mapped[float] = mapped_column(Float)
    duration_ms: Mapped[int | None] = mapped_column(Integer)
