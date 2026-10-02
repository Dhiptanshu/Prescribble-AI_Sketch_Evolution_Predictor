"""Run Alembic migrations programmatically (used at start-up in dev and by the container entrypoint)."""
from pathlib import Path

from alembic import command
from alembic.config import Config

API_DIR = Path(__file__).resolve().parent.parent


def alembic_config(database_url: str | None = None) -> Config:
    cfg = Config(str(API_DIR / "alembic.ini"))
    cfg.set_main_option("script_location", str(API_DIR / "alembic"))
    if database_url:
        cfg.set_main_option("sqlalchemy.url", database_url.replace("%", "%%"))
    return cfg


def run_migrations(database_url: str) -> None:
    command.upgrade(alembic_config(database_url), "head")
