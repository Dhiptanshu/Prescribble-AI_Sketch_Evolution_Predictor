"""Database backups for the SQLite deployment (PostgreSQL: use pg_dump, see docs/DEPLOY.md).

Uses SQLite's online backup API, so the copy is consistent even while the app is writing (copying the .db file with `cp` can catch a half-written page).
Every backup is opened and checked before it counts, and only the newest `keep` are kept.
"""
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

PREFIX = "prescribble-"
TABLES = ("users", "drawings", "challenge_attempts", "rooms", "round_submissions", "api_keys")


class BackupError(Exception):
    pass


def sqlite_path(database_url: str) -> Path:
    """The file behind sqlite:///relative, sqlite:////absolute or sqlite:///C:/windows/path URLs."""
    if not database_url.startswith("sqlite:///") or ":memory:" in database_url:
        raise BackupError("this command backs up SQLite files; for PostgreSQL run pg_dump (see docs/DEPLOY.md)")
    path = Path(database_url[len("sqlite:///"):])
    if not path.is_file():
        raise BackupError(f"no database file at {path}")
    return path


def check(path: Path) -> dict[str, int]:
    """Open a backup, run SQLite's integrity check and count the rows of the main tables."""
    if not path.is_file():
        raise BackupError(f"no backup file at {path}")
    con = sqlite3.connect(f"file:{path.as_posix()}?mode=ro", uri=True)
    try:
        if con.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
            raise BackupError(f"{path.name} failed SQLite's integrity check")
        existing = {r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        return {t: con.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0] for t in TABLES if t in existing}
    except sqlite3.DatabaseError as e:                 # not a database at all, or damaged beyond the integrity check
        raise BackupError(f"{path.name} is not a readable SQLite database: {e}") from e
    finally:
        con.close()


def backup(database_url: str, out_dir: Path, keep: int = 14, now: datetime | None = None) -> tuple[Path, dict[str, int]]:
    """Write a verified copy into `out_dir` and prune old ones. Returns the new file and the row counts found in it."""
    source = sqlite_path(database_url)
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = (now or datetime.now(timezone.utc)).strftime("%Y%m%d-%H%M%S")
    target = out_dir / f"{PREFIX}{stamp}.db"
    src, dst = sqlite3.connect(source), sqlite3.connect(target)
    try:
        src.backup(dst)
    finally:
        dst.close()
        src.close()
    try:
        counts = check(target)
    except Exception:
        target.unlink(missing_ok=True)                # a copy that does not verify is not a backup
        raise
    for old in sorted(out_dir.glob(f"{PREFIX}*.db"))[:-keep] if keep > 0 else []:
        old.unlink()
    return target, counts


def restore(backup_file: Path, database_url: str) -> Path:
    """Put a verified backup in place of the database file (the old file is kept next to it as .before-restore). Stop the app first."""
    check(backup_file)
    path = Path(database_url[len("sqlite:///"):]) if database_url.startswith("sqlite:///") else None
    if path is None:
        raise BackupError("restore works on SQLite files only")
    if path.exists():
        path.replace(path.with_name(path.name + ".before-restore"))
    for side in ("-wal", "-shm"):                      # write-ahead-log leftovers of the replaced database must not be replayed onto the restored one
        path.with_name(path.name + side).unlink(missing_ok=True)
    path.write_bytes(backup_file.read_bytes())
    return path
