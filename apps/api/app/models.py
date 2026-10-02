"""ORM models. Keep one class per table; relationships are added as features land."""
from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, String
from sqlalchemy.orm import Mapped, mapped_column

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
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
