"""Operator commands. Admins are promoted here, on the server, never through the public API.

python -m app.cli make-admin someone@example.com
python -m app.cli remove-admin someone@example.com
python -m app.cli export-training --out training.jsonl     # consented, label-confirmed drawings of the live model's classes, no account identity
python -m app.cli backup --out /backups [--keep 14]         # a verified, consistent copy of the SQLite database; prunes to the newest 14
python -m app.cli restore --from /backups/prescribble-....db   # put a backup back (stop the app first)
"""
import argparse
import json
import sys
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.classes import known_classes
from app.config import get_settings
from app.db import make_engine, make_session_factory
from app.models import User
from app.services import backup as backups
from app.services import training_data
from app.services.registry import active_version


def set_admin(db: Session, email: str, value: bool) -> bool:
    """Returns False when no account has that email."""
    user = db.scalar(select(User).where(User.email == email.strip().lower()))
    if user is None:
        return False
    user.is_admin = value
    db.commit()
    return True


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m app.cli")
    parser.add_argument("command", choices=["make-admin", "remove-admin", "export-training", "backup", "restore"])
    parser.add_argument("email", nargs="?")
    parser.add_argument("--out", help="export-training: file to write (one JSON object per line)")
    parser.add_argument("--version", help="export-training: model version whose classes to keep (default: the live one)")
    parser.add_argument("--keep", type=int, default=14, help="backup: how many of the newest backups to keep")
    parser.add_argument("--from", dest="source", help="restore: the backup file to put back")
    args = parser.parse_args(argv)
    settings = get_settings()
    if args.command in ("backup", "restore"):
        try:
            if args.command == "backup":
                if not args.out:
                    parser.error("backup needs --out")
                target, counts = backups.backup(settings.database_url, Path(args.out), args.keep)
                print(f"backed up to {target} (verified: {', '.join(f'{n} {t}' for t, n in counts.items())})")
            else:
                if not args.source:
                    parser.error("restore needs --from")
                print(f"restored {backups.restore(Path(args.source), settings.database_url)} (the previous file is kept as .before-restore)")
        except backups.BackupError as e:
            print(f"failed: {e}", file=sys.stderr)
            return 1
        return 0
    engine = make_engine(settings.database_url)
    if args.command == "export-training":
        if not args.out:
            parser.error("export-training needs --out")
        with make_session_factory(engine)() as db:
            records = training_data.export_records(db, known_classes(settings, args.version or active_version(settings)))
        with open(args.out, "w", encoding="utf-8") as f:
            f.writelines(json.dumps(r) + chr(10) for r in records)
        print(f"wrote {len(records)} drawings to {args.out}")
        return 0
    if not args.email:
        parser.error(f"{args.command} needs an email")
    with make_session_factory(engine)() as db:
        if not set_admin(db, args.email, args.command == "make-admin"):
            print(f"No account with email {args.email}", file=sys.stderr)
            return 1
    print(f"{args.email} is {'now' if args.command == 'make-admin' else 'no longer'} an admin")
    return 0


if __name__ == "__main__":
    sys.exit(main())
