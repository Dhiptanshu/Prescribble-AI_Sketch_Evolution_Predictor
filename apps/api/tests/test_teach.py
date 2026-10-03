"""Teaching the AI and the training-data rules: consent, confirmed labels, exports without identity, and withdrawal."""
import json
import sys

import pytest
from fastapi.testclient import TestClient

from app.cli import main as cli_main
from app.cli import set_admin
from tests.conftest import REPO_MODELS, build_app

sys.path.insert(0, str(REPO_MODELS.parent))
from src.flywheel import dataset                                   # noqa: E402

API = "/api/v1"
STROKES = [[[20, 20], [200, 25], [205, 190], [25, 200], [20, 20]]]
CLASSES = json.loads((REPO_MODELS / "v1" / "meta.json").read_text(encoding="utf-8"))["classes"]


@pytest.fixture
def app(clock, scorer):
    return build_app(clock, scorer, writes_per_minute=10_000)


def draw(c, label="house", mode="free", confirmed=False, input_type=None, ai_guess="house", strokes=STROKES, version="v1"):
    body = {"strokes": strokes, "label": label, "ai_guess": ai_guess, "ai_confidence": 0.8, "mode": mode, "model_version": version, "label_confirmed": confirmed}
    if input_type:
        body["input_type"] = input_type
    return c.post(f"{API}/drawings", json=body)


def consent(c, on=True):
    assert c.patch(f"{API}/me", json={"consent_training": on}).status_code == 200


@pytest.fixture
def run_export(app, tmp_path, monkeypatch):
    """Run the real CLI against the app's own database and return the exported records."""
    import app.cli as cli

    def _run():
        out = tmp_path / "training.jsonl"
        monkeypatch.setattr(cli, "get_settings", lambda: app.state.settings)
        monkeypatch.setattr(cli, "make_engine", lambda url: app.state.engine)
        assert cli_main(["export-training", "--out", str(out)]) == 0
        return dataset.read_jsonl(out)
    return _run


# ---------------------------------------------------------------- consent and confirmation

def test_a_label_the_person_never_checked_is_not_training_data(client, make_user, run_export):
    make_user()
    consent(client)
    assert draw(client, confirmed=False).json()["label_confirmed"] is False               # saved with the AI's guess, never checked
    assert draw(client, confirmed=True, strokes=[[[5, 5], [100, 100]]]).json()["label_confirmed"] is True
    assert [r["label"] for r in run_export()] == ["house"] and len(run_export()) == 1


def test_confirmation_needs_a_label(client, make_user):
    make_user()
    assert draw(client, label=None, confirmed=True).json()["label_confirmed"] is False


def test_choosing_a_label_afterwards_confirms_it_and_clearing_unconfirms(client, make_user):
    make_user()
    d = draw(client).json()
    assert d["label_confirmed"] is False
    assert client.patch(f"{API}/drawings/{d['id']}", json={"label": "cat"}).json()["label_confirmed"] is True
    assert client.patch(f"{API}/drawings/{d['id']}", json={"label": None}).json()["label_confirmed"] is False


def test_nothing_is_exported_without_consent_and_revoking_it_removes_the_drawings(client, make_user, run_export):
    make_user()
    draw(client, confirmed=True)
    assert run_export() == []                                                           # consent is off by default
    consent(client)
    assert len(run_export()) == 1
    consent(client, False)
    assert run_export() == []                                                           # a later export no longer contains them


def test_labels_must_be_classes_of_the_model_and_duplicates_collapse(client, make_user, run_export, app):
    make_user()
    consent(client)
    draw(client, confirmed=True)
    draw(client, confirmed=True)                                                        # exact duplicate
    from app.models import Drawing
    with app.state.session_factory() as db:
        db.add(Drawing(user_id=1, label="spaceship", ai_guess="house", ai_confidence=.5, mode="free", model_version="v1", strokes=[[[1, 2], [3, 4]]],
                       n_strokes=1, ink=2.8, label_confirmed=True))
        db.commit()
    assert [r["label"] for r in run_export()] == ["house"]


def test_the_export_carries_no_identity_and_is_stable(client, make_user, run_export):
    make_user("secret.person@example.com", "Secret Person")
    consent(client)
    draw(client, confirmed=True, input_type="mouse")
    first, again = run_export(), run_export()
    text = json.dumps(first)
    assert "example.com" not in text and "Secret" not in text and "user_id" not in text
    assert first == again and len(first[0]["uid"]) == 16 and first[0]["input_type"] == "mouse" and first[0]["source"] == "free"


def test_the_flywheel_reads_the_export_and_splits_it_stably(client, make_user, run_export):
    make_user()
    consent(client)
    for i in range(30):
        draw(client, confirmed=True, strokes=[[[i, 1], [i + 50, 90]]])
    records = run_export()
    train, held = dataset.split(records)
    assert len(train) + len(held) == 30 and held and train                              # about one in five is held out
    assert dataset.split(run_export()) == (train, held)                                 # and the same drawings every time


# ---------------------------------------------------------------- teach

def test_teaching_needs_consent_and_a_word(client, make_user):
    make_user()
    assert client.get(f"{API}/teach/next").json()["error"]["code"] == "consent_required"
    assert draw(client, mode="teach").json()["error"]["code"] == "consent_required"
    consent(client)
    assert draw(client, label=None, mode="teach").status_code == 409                    # a teaching drawing is always of a given word


def test_teach_gives_the_least_covered_word_and_not_the_one_just_drawn(client, make_user):
    make_user()
    consent(client)
    for word in CLASSES[:-1]:
        assert draw(client, label=word, mode="teach", ai_guess=word).status_code == 201
    nxt = client.get(f"{API}/teach/next").json()
    assert nxt["target"] == CLASSES[-1]                                                  # every other word already has an example
    assert nxt["summary"]["mine"] == 29 and nxt["summary"]["ready_total"] == 29 and nxt["summary"]["classes_covered"] == 29
    assert nxt["summary"]["classes_total"] == 30 and nxt["summary"]["model_version"] == "v1"
    draw(client, label=CLASSES[-1], mode="teach", ai_guess=CLASSES[-1], strokes=[[[9, 9], [90, 90]]])
    avoided = client.get(f"{API}/teach/next", params={"avoid": "cat"}).json()["target"]
    assert avoided != "cat"


def test_teach_drawings_are_confirmed_and_kept_out_of_the_gallery_stats_and_quota(app, clock, scorer, make_user, client):
    app.state.settings.max_drawings_per_user = 1
    make_user()
    consent(client)
    t = draw(client, label="cat", mode="teach", ai_guess="dog", input_type="touch").json()
    assert t["label_confirmed"] is True and t["input_type"] == "touch" and t["mode"] == "teach"
    assert client.get(f"{API}/drawings").json()["items"] == []                            # not in the gallery
    assert client.get(f"{API}/me/stats").json()["total"] == 0                              # nor the personal stats
    assert draw(client, strokes=[[[1, 1], [50, 50]]]).status_code == 201                    # the saved-drawings quota is untouched
    assert draw(client, strokes=[[[2, 2], [60, 60]]]).json()["error"]["code"] == "quota_exceeded"


def test_teaching_has_its_own_cap(app, client, make_user):
    app.state.settings.max_teach_per_user = 2
    make_user()
    consent(client)
    for i in range(2):
        assert draw(client, mode="teach", strokes=[[[i, 1], [60, 60]]]).status_code == 201
    assert draw(client, mode="teach", strokes=[[[9, 1], [60, 60]]]).json()["error"]["code"] == "quota_exceeded"


def test_withdrawing_deletes_only_teaching_contributions(client, make_user, run_export):
    make_user()
    consent(client)
    draw(client, mode="teach", label="cat", ai_guess="cat")
    keep = draw(client, confirmed=True, strokes=[[[7, 7], [70, 70]]]).json()
    assert client.delete(f"{API}/teach/contributions").json() == {"deleted": 1}
    assert [r["label"] for r in run_export()] == ["house"]
    assert client.get(f"{API}/drawings/{keep['id']}").status_code == 200


def test_teach_contributions_go_in_the_users_own_data_export(client, make_user):
    make_user()
    consent(client)
    draw(client, mode="teach", label="cat", ai_guess="cat")
    exported = client.get(f"{API}/me/export").json()
    assert any(d["mode"] == "teach" for d in exported["drawings"])


# ---------------------------------------------------------------- admin view

def test_admin_sees_how_much_training_data_is_ready(app, client, make_user):
    make_user("boss@example.com", "Boss")
    with app.state.session_factory() as db:
        set_admin(db, "boss@example.com", True)
    consent(client)
    draw(client, mode="teach", label="cat", ai_guess="cat", input_type="mouse")
    draw(client, mode="teach", label="dog", ai_guess="dog", input_type="touch")
    draw(client, confirmed=False, strokes=[[[4, 4], [40, 40]]])                         # not confirmed: not counted
    t = client.get(f"{API}/admin/metrics").json()["training"]
    assert t == {"ready": 2, "classes_covered": 2, "classes_total": 30, "contributors": 1, "by_input_type": {"mouse": 1, "touch": 1}}
