"""Backups: consistent, verified, pruned, restorable. A real SQLite file is used (the in-memory test database cannot be backed up by file)."""
import sqlite3
import threading
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import app.cli as cli
from app.services import backup as backups
from tests.conftest import PASSWORD, build_app

API = "/api/v1"
DRAWING = {"strokes": [[[20, 20], [200, 25], [205, 190]]], "label": "house", "ai_guess": "house", "ai_confidence": 0.9, "model_version": "v1"}


@pytest.fixture
def live(tmp_path, clock, scorer):
    """An app on a real database file with one account and one drawing in it."""
    url = f"sqlite:///{(tmp_path / 'live.db').as_posix()}"
    app = build_app(clock, scorer, database_url=url, writes_per_minute=10_000)
    with TestClient(app) as c:
        assert c.post(f"{API}/auth/register", json={"email": "ada@example.com", "password": PASSWORD, "display_name": "Ada"}).status_code == 201
        assert c.post(f"{API}/drawings", json=DRAWING).status_code == 201
        yield url, c


def rows(db_file: Path, table: str) -> int:
    con = sqlite3.connect(db_file)
    try:
        return con.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
    finally:
        con.close()


def test_a_backup_is_a_verified_copy_with_the_same_rows(live, tmp_path):
    url, _ = live
    target, counts = backups.backup(url, tmp_path / "out")
    assert target.name.startswith("prescribble-") and counts["users"] == 1 and counts["drawings"] == 1
    assert rows(target, "users") == 1 and rows(target, "drawings") == 1


def test_a_backup_taken_while_the_app_is_writing_is_still_consistent(live, tmp_path):
    url, client = live
    stop = threading.Event()

    def write():
        i = 0
        while not stop.is_set():
            client.post(f"{API}/drawings", json={**DRAWING, "strokes": [[[i % 200, 1], [i % 200 + 5, 90]]]})
            i += 1

    t = threading.Thread(target=write)
    t.start()
    try:
        results = [backups.backup(url, tmp_path / "out", keep=50, now=datetime(2026, 1, 1, tzinfo=timezone.utc) + timedelta(seconds=k)) for k in range(5)]
    finally:
        stop.set()
        t.join()
    assert all(c["users"] == 1 and c["drawings"] >= 1 for _, c in results)                    # every copy passed SQLite's integrity check and is readable
    assert [c["drawings"] for _, c in results] == sorted(c["drawings"] for _, c in results)   # and each later copy has at least as much as the earlier one


def test_only_the_newest_backups_are_kept(live, tmp_path):
    url, _ = live
    start = datetime(2026, 10, 1, tzinfo=timezone.utc)
    for day in range(5):
        backups.backup(url, tmp_path / "out", keep=3, now=start + timedelta(days=day))
    kept = sorted(p.name for p in (tmp_path / "out").glob("prescribble-*.db"))
    assert kept == ["prescribble-20261003-000000.db", "prescribble-20261004-000000.db", "prescribble-20261005-000000.db"]


def test_postgres_and_memory_databases_are_refused_with_advice(tmp_path):
    with pytest.raises(backups.BackupError, match="pg_dump"):
        backups.backup("postgresql+psycopg://u:p@db/prescribble", tmp_path)
    with pytest.raises(backups.BackupError, match="pg_dump"):
        backups.backup("sqlite://", tmp_path)
    with pytest.raises(backups.BackupError, match="no database file"):
        backups.backup(f"sqlite:///{(tmp_path / 'missing.db').as_posix()}", tmp_path)


def test_a_damaged_file_is_not_accepted_as_a_backup_or_restored(live, tmp_path):
    url, _ = live
    bad = tmp_path / "prescribble-bad.db"
    bad.write_bytes(b"this is not a database" * 100)
    with pytest.raises(backups.BackupError, match="not a readable SQLite database"):
        backups.check(bad)
    with pytest.raises(backups.BackupError):
        backups.restore(bad, url)
    assert rows(Path(url[len("sqlite:///"):]), "users") == 1                                  # the live database was not touched


def test_restore_puts_the_data_back_and_keeps_the_old_file(live, tmp_path):
    url, client = live
    target, _ = backups.backup(url, tmp_path / "out")
    assert client.request("DELETE", f"{API}/me", json={"password": PASSWORD}).status_code == 204
    db_file = Path(url[len("sqlite:///"):])
    assert rows(db_file, "users") == 0
    client.app.state.engine.dispose()                                                         # the app is stopped while its file is replaced
    backups.restore(target, url)
    assert rows(db_file, "users") == 1 and rows(db_file, "drawings") == 1
    assert rows(db_file.with_name(db_file.name + ".before-restore"), "users") == 0           # the file that was replaced is still there


def test_the_command_line_backs_up_and_restores(live, tmp_path, monkeypatch, capsys):
    url, client = live
    settings = client.app.state.settings
    monkeypatch.setattr(cli, "get_settings", lambda: settings)
    assert cli.main(["backup", "--out", str(tmp_path / "cli")]) == 0
    printed = capsys.readouterr().out
    assert "verified" in printed and "1 users" in printed and "1 drawings" in printed
    made = next((tmp_path / "cli").glob("prescribble-*.db"))
    client.app.state.engine.dispose()
    assert cli.main(["restore", "--from", str(made)]) == 0
    assert cli.main(["restore", "--from", str(tmp_path / "nope.db")]) == 1
    assert "failed" in capsys.readouterr().err
