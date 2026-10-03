from alembic import command
from sqlalchemy import create_engine, inspect

from app.migrations import alembic_config, run_migrations


def test_migrations_upgrade_and_downgrade(tmp_path):
    url = f"sqlite:///{tmp_path / 'm.db'}"
    run_migrations(url)
    engine = create_engine(url)
    assert {"users", "drawings", "daily_challenges", "challenge_attempts"} <= set(inspect(engine).get_table_names())
    cols = {c["name"] for c in inspect(engine).get_columns("users")}
    assert {"email", "password_hash", "display_name", "is_admin", "consent_training", "show_on_leaderboard", "created_at"} <= cols
    fks = inspect(engine).get_foreign_keys("drawings")
    assert fks and fks[0]["referred_table"] == "users" and fks[0]["options"].get("ondelete") == "CASCADE"
    command.downgrade(alembic_config(url), "base")
    left = set(inspect(create_engine(url)).get_table_names())
    assert not ({"users", "drawings", "daily_challenges", "challenge_attempts"} & left)
    engine.dispose()
