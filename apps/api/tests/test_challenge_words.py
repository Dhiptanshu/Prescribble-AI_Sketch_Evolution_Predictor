"""Daily and round words come only from classes the model measurably recognises (when its results say which those are)."""
import json
import shutil

from fastapi.testclient import TestClient

from app.services.daily import challenge_classes
from tests.conftest import REPO_MODELS, make_settings
from app.main import create_app

API = "/api/v1"


def meta(per_class, classes=("a", "b", "c", "d")):
    return {"classes": list(classes), "test_results": {"0.5": {"top1": 0.5, "top5": 0.9, "per_class_top1": per_class}}}


def test_only_classes_the_model_recognises_by_half_the_ink_are_eligible():
    assert challenge_classes(meta([0.9, 0.2, 0.5, 0.49])) == ["a", "c"]                      # the bar is 50% Top-1, inclusive


def test_a_model_without_per_class_numbers_offers_every_class():
    assert challenge_classes({"classes": ["a", "b"], "test_results": {"0.5": {"top1": 0.5}}}) == ["a", "b"]
    assert challenge_classes({"classes": ["a", "b"]}) == ["a", "b"]


def test_if_no_class_clears_the_bar_the_word_still_comes_from_the_model():
    assert challenge_classes(meta([0.1, 0.2, None, 0.3])) == ["a", "b", "c", "d"]


def test_the_daily_word_and_round_words_are_drawn_from_the_eligible_classes(tmp_path, clock):
    shutil.copytree(REPO_MODELS / "v1", tmp_path / "v1")
    m = json.loads((tmp_path / "v1" / "meta.json").read_text(encoding="utf-8"))
    m["test_results"]["0.5"]["per_class_top1"] = [0.95 if c in ("cat", "dog") else 0.1 for c in m["classes"]]
    (tmp_path / "v1" / "meta.json").write_text(json.dumps(m), encoding="utf-8")
    app = create_app(make_settings(models_dir=tmp_path, writes_per_minute=1000), clock=clock)
    with TestClient(app) as c:
        words = set()
        for _ in range(8):
            words.add(c.get(f"{API}/challenge/today").json()["target"])
            clock.advance(days=1)
        assert words <= {"cat", "dog"}
        assert c.post(f"{API}/auth/register", json={"email": "t@example.com", "password": "correct horse battery", "display_name": "T"}).status_code == 201
        room = c.post(f"{API}/rooms", json={"name": "r"}).json()
        started = c.post(f"{API}/rooms/{room['id']}/rounds", json={"duration_s": 30}).json()
        assert started["round"]["target"] in {"cat", "dog"}
        clock.advance(minutes=5)
        # a teacher may still pick any class the model knows
        assert c.post(f"{API}/rooms/{room['id']}/rounds", json={"target": "house", "duration_s": 30}).status_code == 201
