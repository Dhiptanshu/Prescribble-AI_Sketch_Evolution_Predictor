from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app

PASSWORD = "correct horse battery"
REPO_MODELS = Path(__file__).resolve().parents[3] / "models"      # the real model metadata: class names are validated against it


def make_settings(**overrides) -> Settings:
    base = dict(env="test", database_url="sqlite://", secret_key="t" * 48, auth_attempts_per_minute=1000, models_dir=REPO_MODELS)
    return Settings(**{**base, **overrides})


@pytest.fixture
def client():
    with TestClient(create_app(make_settings())) as c:
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
