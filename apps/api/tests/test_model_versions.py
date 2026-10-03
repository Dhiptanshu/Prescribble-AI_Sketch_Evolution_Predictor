"""The API follows models/registry.json: promoting a version ships it without any code change. Real model files, copied under new names."""
import json
import shutil
import sys

import pytest
from fastapi.testclient import TestClient

from app.cli import set_admin
from app.main import create_app
from tests.conftest import PASSWORD, REPO_MODELS, make_settings, strokes_of

sys.path.insert(0, str(REPO_MODELS.parent))                        # the registry library lives in the repo's src/
from src.flywheel import registry                                  # noqa: E402

API = "/api/v1"


@pytest.fixture
def models_dir(tmp_path):
    """A models folder with the real v1 registered and live, plus an identical v1b registered as a candidate."""
    shutil.copytree(REPO_MODELS / "v1", tmp_path / "v1")
    shutil.copytree(REPO_MODELS / "v1", tmp_path / "v1b")
    registry.register("v1", tmp_path)
    registry.register("v1b", tmp_path, parent="v1")
    return tmp_path


def make_app(models_dir, clock, **settings):
    """No scorer is injected: the app resolves and loads the model itself, as in production."""
    return create_app(make_settings(models_dir=models_dir, **settings), clock=clock)


def promote_on_disk(models_dir, version):
    reg = registry.load(models_dir)
    reg["active"] = version                                         # what a successful `registry promote` writes
    registry.save(reg, models_dir)


def test_the_live_version_comes_from_the_registry(models_dir, clock):
    with TestClient(make_app(models_dir, clock)) as c:
        assert c.get(f"{API}/model").json()["version"] == "v1"
        promote_on_disk(models_dir, "v1b")
    with TestClient(make_app(models_dir, clock)) as c:              # a fresh process reads the new live version
        assert c.get(f"{API}/model").json()["version"] == "v1b"


def test_an_operator_can_pin_a_version_over_the_registry(models_dir, clock):
    promote_on_disk(models_dir, "v1b")
    with TestClient(make_app(models_dir, clock, model_version="v1")) as c:
        assert c.get(f"{API}/model").json()["version"] == "v1"


def test_without_a_registry_the_version_is_v1(tmp_path, clock):
    shutil.copytree(REPO_MODELS / "v1", tmp_path / "v1")
    with TestClient(make_app(tmp_path, clock)) as c:
        assert c.get(f"{API}/model").json()["version"] == "v1"
        assert c.get(f"{API}/models").json()["versions"] == []


def test_the_models_listing_is_public_and_leaks_no_hashes(models_dir, clock):
    with TestClient(make_app(models_dir, clock)) as c:
        body = c.get(f"{API}/models").json()
    assert body["active"] == "v1" and [v["version"] for v in body["versions"]] == ["v1", "v1b"]
    live = {v["version"]: v["live"] for v in body["versions"]}
    assert live == {"v1": True, "v1b": False}
    assert body["versions"][0]["n_classes"] == 30 and body["versions"][0]["metrics"]["quickdraw_test_top5_at_30"] > 0.9
    assert "sha256" not in json.dumps(body) and "notes" not in json.dumps(body)


def test_reload_switches_the_live_model_without_a_restart_and_is_admin_only(models_dir, clock):
    app = make_app(models_dir, clock)
    with TestClient(app) as c, TestClient(app) as stranger:
        assert c.post(f"{API}/auth/register", json={"email": "ops@example.com", "password": PASSWORD, "display_name": "Ops"}).status_code == 201
        assert c.post(f"{API}/admin/model/reload").status_code == 403
        with app.state.session_factory() as db:
            set_admin(db, "ops@example.com", True)
        assert stranger.post(f"{API}/admin/model/reload").status_code == 401
        assert c.get(f"{API}/model").json()["version"] == "v1"
        promote_on_disk(models_dir, "v1b")
        assert c.get(f"{API}/model").json()["version"] == "v1"           # still the loaded one until reloaded
        assert c.post(f"{API}/admin/model/reload").json() == {"active": "v1b"}
        assert c.get(f"{API}/model").json()["version"] == "v1b"
        assert c.get(f"{API}/admin/metrics").json()["model_version"] == "v1b"


def test_a_running_challenge_day_stays_on_the_model_it_started_with(models_dir, clock):
    """Switching models mid-day must not change how that day's attempts are scored."""
    app = make_app(models_dir, clock)
    with TestClient(app) as c:
        assert c.post(f"{API}/auth/register", json={"email": "p@example.com", "password": PASSWORD, "display_name": "P"}).status_code == 201
        day = c.get(f"{API}/challenge/today").json()
        assert day["model_version"] == "v1"
        promote_on_disk(models_dir, "v1b")
        ops = TestClient(app)                                           # no `with`: leaving a second lifespan would drop the in-memory database
        if True:
            ops.post(f"{API}/auth/register", json={"email": "o@example.com", "password": PASSWORD, "display_name": "O"})
            with app.state.session_factory() as db:
                set_admin(db, "o@example.com", True)
            assert ops.post(f"{API}/admin/model/reload").json()["active"] == "v1b"
        assert c.get(f"{API}/challenge/today").json()["model_version"] == "v1"           # frozen for the day
        r = c.post(f"{API}/challenge/attempts", json={"strokes": strokes_of(day["target"])[0], "duration_ms": 3000})
        assert r.status_code == 200
        assert "v1" in app.state.scorers and app.state.scorers["v1"].version == "v1"      # scored by v1, not the new live model


def test_the_registry_file_is_revalidated_but_versioned_models_stay_immutable(models_dir, clock, tmp_path):
    dist = tmp_path / "dist"
    (dist / "models" / "v1").mkdir(parents=True)
    (dist / "index.html").write_text("<html></html>")
    (dist / "models" / "v1" / "meta.json").write_text("{}")
    (dist / "models" / "registry.json").write_text(json.dumps({"active": "v1"}))
    app = create_app(make_settings(web_dist=dist, models_dir=models_dir))
    with TestClient(app) as web:
        assert "immutable" in web.get("/models/v1/meta.json").headers["cache-control"]
        reg = web.get("/models/registry.json")
        assert reg.headers["cache-control"] == "no-cache" and reg.json() == {"active": "v1"}      # a promotion must be seen on the next load
        assert reg.headers["access-control-allow-origin"] == "*"                                   # the widget on other sites reads it too


def test_the_registry_library_and_the_servers_scorer_agree(models_dir, clock, scorer):
    """The promotion gate measures with src/flywheel/onnx_eval.py, so it must score exactly like the server does."""
    import numpy as np

    from app.inference import _as_array
    from src.flywheel.onnx_eval import OnnxModel
    sketch = strokes_of("cat")[0]
    mine = OnnxModel("v1", REPO_MODELS)
    for f in (0.2, 0.5, 1.0):
        assert np.allclose(mine.probabilities(_as_array(sketch), f), scorer.probabilities(_as_array(sketch), f), atol=1e-6)
