"""Database engine / session helpers."""
from collections.abc import Iterator

from fastapi import Request
from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker
from sqlalchemy.pool import StaticPool


class Base(DeclarativeBase):
    """Declarative base for all ORM models."""


def make_engine(url: str) -> Engine:
    kwargs: dict = {}
    if url.startswith("sqlite"):
        kwargs["connect_args"] = {"check_same_thread": False}
        if ":memory:" in url or url in ("sqlite://", "sqlite:///"):
            kwargs["poolclass"] = StaticPool       # one shared in-memory DB (tests)
    engine = create_engine(url, pool_pre_ping=True, **kwargs)
    if url.startswith("sqlite"):
        in_memory = ":memory:" in url or url in ("sqlite://", "sqlite:///")

        @event.listens_for(engine, "connect")
        def _pragmas(dbapi_conn, _):
            dbapi_conn.execute("PRAGMA foreign_keys=ON")            # SQLite ignores foreign keys unless asked
            if not in_memory:
                # Write-ahead logging lets readers run while one writer commits, and synchronous=NORMAL is safe with it (a crash can lose the last
                # commit but never corrupt the file). Without this every request that records usage queued behind the one before it on a file lock.
                dbapi_conn.execute("PRAGMA journal_mode=WAL")
                dbapi_conn.execute("PRAGMA synchronous=NORMAL")
                dbapi_conn.execute("PRAGMA busy_timeout=30000")
    return engine


def make_session_factory(engine: Engine) -> sessionmaker[Session]:
    return sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def get_db(request: Request) -> Iterator[Session]:
    db = request.app.state.session_factory()
    try:
        yield db
    finally:
        db.close()
