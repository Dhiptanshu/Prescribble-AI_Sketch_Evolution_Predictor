"""Operator commands. Admins are promoted here, on the server, never through the public API.

python -m app.cli make-admin someone@example.com
python -m app.cli remove-admin someone@example.com
"""
import argparse
import sys

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db import make_engine, make_session_factory
from app.models import User


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
    parser.add_argument("command", choices=["make-admin", "remove-admin"])
    parser.add_argument("email")
    args = parser.parse_args(argv)
    engine = make_engine(get_settings().database_url)
    with make_session_factory(engine)() as db:
        if not set_admin(db, args.email, args.command == "make-admin"):
            print(f"No account with email {args.email}", file=sys.stderr)
            return 1
    print(f"{args.email} is {'now' if args.command == 'make-admin' else 'no longer'} an admin")
    return 0


if __name__ == "__main__":
    sys.exit(main())
