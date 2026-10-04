import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.inference import Scorer
from app.main import create_app

PASSWORD = "correct horse battery"
REPO_MODELS = Path(__file__).resolve().parents[3] / "models"      # the real model metadata: class names are validated against it


def make_settings(**overrides) -> Settings:
    # model_version is pinned to the fixture model (v1) so the tests do not depend on which version the repo has live; the version tests pass None
    base = dict(env="test", database_url="sqlite://", secret_key="t" * 48, auth_attempts_per_minute=1000, models_dir=REPO_MODELS, model_version="v1")
    return Settings(**{**base, **overrides})


T0 = datetime(2026, 10, 3, 12, 0, tzinfo=timezone.utc)
SAMPLES = json.loads((REPO_MODELS / "v1" / "samples.json").read_text(encoding="utf-8"))      # real held-out QuickDraw sketches


def strokes_of(label):
    return [s["strokes"] for s in SAMPLES if s["label"] == label]


class Clock:
    """A controllable UTC clock so tests can move between days."""

    def __init__(self, start):
        self.now = start

    def __call__(self):
        return self.now

    def advance(self, **kw):
        self.now += timedelta(**kw)


@pytest.fixture(scope="session")
def scorer():
    return Scorer(REPO_MODELS, "v1")


@pytest.fixture(scope="session")
def live_scorer():
    """The model the repo currently has live (models/registry.json), for tests that guard what is shown to people."""
    return Scorer(REPO_MODELS, json.loads((REPO_MODELS / "registry.json").read_text(encoding="utf-8"))["active"])


@pytest.fixture
def clock():
    return Clock(T0)


def build_app(clock, scorer, **overrides):
    application = create_app(make_settings(**overrides), clock=clock)
    application.state.scorer = scorer               # share the loaded model between tests
    return application


@pytest.fixture
def app(clock, scorer):
    return build_app(clock, scorer)


@pytest.fixture
def client(app):
    with TestClient(app) as c:
        yield c


@pytest.fixture
def other_client(client):
    """A second, independent browser (separate cookie jar) talking to the same app and database."""
    with TestClient(client.app) as c:
        yield c


@pytest.fixture
def make_user(client):
    """Register a user on the shared client (which then holds that user's session cookie)."""
    def _make(email="ada@example.com", name="Ada", password=PASSWORD):
        r = client.post("/api/v1/auth/register", json={"email": email, "password": password, "display_name": name})
        assert r.status_code == 201, r.text
        return r.json()
    return _make
