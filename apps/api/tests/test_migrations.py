from alembic import command
from sqlalchemy import create_engine, inspect

from app.migrations import alembic_config, run_migrations


def test_migrations_upgrade_and_downgrade(tmp_path):
    url = f"sqlite:///{tmp_path / 'm.db'}"
    run_migrations(url)
    engine = create_engine(url)
    assert "users" in inspect(engine).get_table_names()
    cols = {c["name"] for c in inspect(engine).get_columns("users")}
    assert {"email", "password_hash", "display_name", "is_admin", "consent_training", "created_at"} <= cols
    command.downgrade(alembic_config(url), "base")
    assert "users" not in inspect(create_engine(url)).get_table_names()
    engine.dispose()
