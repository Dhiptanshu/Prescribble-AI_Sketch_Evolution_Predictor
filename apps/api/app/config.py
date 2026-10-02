"""Application settings, read from PRESCRIBBLE_* environment variables (or a local .env file)."""
import logging
import secrets
from functools import lru_cache
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
    max_strokes: int = 60                     # input limits for submitted drawings
    max_points: int = 2000

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
