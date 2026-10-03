"""Application settings, read from PRESCRIBBLE_* environment variables (or a local .env file)."""
import logging
import secrets
from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

log = logging.getLogger("prescribble.config")


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="PRESCRIBBLE_", env_file=".env", extra="ignore")

    app_name: str = "Prescribble"
    env: Literal["dev", "test", "prod"] = "dev"
    database_url: str = "sqlite:///./prescribble.db"
    auto_migrate: bool = True

    secret_key: str = ""                      # required (>= 32 chars) in prod
    session_minutes: int = 60 * 24 * 14
    cookie_name: str = "prescribble_session"
    cookie_secure: bool | None = None         # defaults to True in prod
    cors_origins: list[str] = ["http://localhost:5173", "http://127.0.0.1:5173"]

    auth_attempts_per_minute: int = 10        # per client IP, register + login
    web_dist: Path | None = None              # built web app to serve (single-container deploys)
    max_strokes: int = 60                     # input limits for submitted drawings
    max_points: int = 2000
    max_drawings_per_user: int = 200          # free-plan quota (saved drawings; teaching contributions have their own)
    max_teach_per_user: int = 1000            # drawings one person may contribute through the Teach page
    writes_per_minute: int = 30               # per signed-in user
    public_reads_per_minute: int = 120        # per client IP, shared-drawing pages
    models_dir: Path | None = None            # folder holding models/<version>/meta.json; auto-detected when unset
    model_version: str | None = None          # pin a model version; unset = the live version in models/registry.json
    ml_root: Path | None = None               # folder containing the `src` training pipeline package; auto-detected when unset
    attempts_per_day: int = 3                 # scored attempts per user per UTC day
    min_attempt_ms: int = 400                 # faster than this is not a human drawing (attempt is kept but not counted)
    max_ink_per_ms: float = 8.0               # frame pixels per millisecond; above this the input looks automated
    api_daily_limit: int = 1000               # predictions per API key per UTC day (stored on each key when it is created)
    api_per_minute: int = 60                  # burst limit per API key
    max_keys_per_user: int = 5                # active API keys per account
    max_open_rooms: int = 10                  # open classrooms per teacher
    max_room_members: int = 60                # students per classroom
    max_rounds_per_room: int = 30
    round_min_s: int = 10                     # a round lasts between these many seconds
    round_max_s: int = 300
    round_grace_s: int = 3                    # after the timer, how long last drawings may still arrive
    joins_per_minute: int = 20                # per client IP (also slows guessing of room codes)

    @model_validator(mode="after")
    def _finalise(self):
        if self.cookie_secure is None:
            self.cookie_secure = self.env == "prod"
        if self.env == "prod" and len(self.secret_key) < 32:
            raise ValueError("PRESCRIBBLE_SECRET_KEY must be at least 32 characters in prod")
        if not self.secret_key:
            self.secret_key = secrets.token_urlsafe(48)
            log.warning("PRESCRIBBLE_SECRET_KEY not set: using a random key (sessions reset on restart)")
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
