"""ORM models. Keep one class per table; relationships are added as features land."""
from datetime import date, datetime, timezone

from sqlalchemy import JSON, Boolean, Date, DateTime, Float, ForeignKey, Index, Integer, String, UniqueConstraint, true
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
    mode: Mapped[str] = mapped_column(String(16), default="free")    # free | challenge
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
