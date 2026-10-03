import json
from datetime import datetime, timedelta, timezone

import numpy as np
import pytest
from fastapi.testclient import TestClient

from app.inference import Scorer, _as_array
from app.main import create_app
from app.models import ChallengeAttempt
from app.services.scoring import FRACTIONS
from tests.conftest import PASSWORD, REPO_MODELS, make_settings

API = "/api/v1/challenge"
T0 = datetime(2026, 10, 3, 12, 0, tzinfo=timezone.utc)
SAMPLES = json.loads((REPO_MODELS / "v1" / "samples.json").read_text(encoding="utf-8"))      # real held-out QuickDraw sketches


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


@pytest.fixture
def clock():
    return Clock(T0)


@pytest.fixture
def app(clock, scorer):
    application = create_app(make_settings(), clock=clock)
    application.state.scorer = scorer               # share the loaded model between tests
    return application


@pytest.fixture
def client(app):
    with TestClient(app) as c:
        yield c


def strokes_of(label):
    return [s["strokes"] for s in SAMPLES if s["label"] == label]


def submit(c, strokes, ms=3000):
    return c.post(f"{API}/attempts", json={"strokes": strokes, "duration_ms": ms})


def new_player(app, name, show=True):
    c = TestClient(app)
    r = c.post("/api/v1/auth/register", json={"email": f"{name.lower().replace(' ', '.')}@example.com", "password": PASSWORD, "display_name": name})
    assert r.status_code == 201, r.text
    if not show:
        assert c.patch("/api/v1/me", json={"show_on_leaderboard": False}).status_code == 200
    return c, r.json()["id"]


def add_attempt(app, user_id, day, score, minutes=0, suspect=False, no=1):
    """Insert a scored attempt directly, to test ranking rules independently of the model."""
    with app.state.session_factory() as db:
        db.add(ChallengeAttempt(user_id=user_id, day=day, attempt_no=no, created_at=T0 + timedelta(minutes=minutes), score=score,
                                recognised_at=None if score == 0 else round(1 - score / 100 + 0.05, 2), final_guess="x", final_confidence=0.5,
                                suspect=suspect, strokes=[[[1, 1], [2, 2]]], n_strokes=1, ink=1.4, duration_ms=1000))
        db.commit()


# ---------------------------------------------------------------- the server really reproduces the model

def test_server_pipeline_agrees_with_the_trained_model_on_real_held_out_sketches(scorer):
    """If the server's preprocessing drifted from training, accuracy on real test sketches would collapse."""
    correct = sum(scorer.classes[int(np.argmax(scorer.probabilities(_as_array(s["strokes"]), 1.0)))] == s["label"] for s in SAMPLES)
    assert correct / len(SAMPLES) >= 0.8, f"only {correct}/{len(SAMPLES)} correct at 100% of the ink"       # the model gets ~90% on this kind of data


def test_early_fractions_are_less_certain_than_the_finished_drawing(scorer):
    gain = []
    for s in SAMPLES:
        raw, idx = _as_array(s["strokes"]), scorer.classes.index(s["label"])
        gain.append(scorer.probabilities(raw, 1.0)[idx] - scorer.probabilities(raw, 0.1)[idx])
    assert np.mean(gain) > 0.1                                       # seeing more of the drawing helps, as the whole project claims


# ---------------------------------------------------------------- today

def test_today_is_public_and_the_word_is_frozen_for_the_day(client, clock, scorer):
    a = client.get(f"{API}/today").json()
    assert a["day"] == "2026-10-03" and a["target"] in scorer.classes and a["model_version"] == "v1"
    assert a["attempts_max"] == 3 and a["seconds_left"] == 12 * 3600 and a["me"] is None
    clock.advance(hours=5)
    b = client.get(f"{API}/today").json()
    assert b["target"] == a["target"] and b["seconds_left"] == 7 * 3600


def test_a_new_day_brings_a_different_word(client, clock):
    first = client.get(f"{API}/today").json()
    clock.advance(days=1)
    second = client.get(f"{API}/today").json()
    assert second["day"] == "2026-10-04" and second["target"] != first["target"]            # never the same word two days running


def test_scoring_requires_an_account(client):
    assert submit(client, strokes_of("cat")[0]).status_code == 401


# ---------------------------------------------------------------- scoring an attempt

def test_a_real_drawing_of_the_word_is_scored_by_the_server(client, make_user):
    make_user()
    target = client.get(f"{API}/today").json()["target"]
    r = submit(client, strokes_of(target)[0])
    assert r.status_code == 200, r.text
    a = r.json()
    assert a["score"] % 5 == 0 and 0 <= a["score"] <= 100 and a["counted"] is True
    assert [t["fraction"] for t in a["timeline"]] == list(FRACTIONS)
    first_hit = next((t for t in a["timeline"] if t["top1"] == target and t["top1_p"] >= 0.5), None)
    assert (a["recognised_at"] if first_hit else None) == (first_hit["fraction"] if first_hit else None)       # score follows the timeline
    assert a["score"] == (0 if first_hit is None else round((1 - first_hit["fraction"]) * 100) + 5)
    assert a["final_guess"] == a["timeline"][-1]["top1"] and a["attempts_left"] == 2
    assert a["rank"] == 1 and a["participants"] == 1


def test_a_scribble_does_not_get_credit(client, make_user):
    make_user()
    r = submit(client, [[[10, 10], [245, 245]]]).json()                       # one straight diagonal line
    assert r["score"] == 0 and r["recognised_at"] is None


def test_the_client_cannot_choose_its_own_score(client, make_user):
    make_user()
    r = client.post(f"{API}/attempts", json={"strokes": [[[10, 10], [245, 245]]], "duration_ms": 3000, "score": 100, "recognised_at": 0.05})
    assert r.status_code == 200 and r.json()["score"] == 0                    # unknown fields are ignored; the model decides


def test_three_attempts_a_day_then_the_best_counts(client, make_user):
    make_user()
    target = client.get(f"{API}/today").json()["target"]
    scores = [submit(client, s).json()["score"] for s in strokes_of(target)[:3]]
    over = submit(client, strokes_of(target)[0])
    assert over.status_code == 409 and over.json()["error"]["code"] == "attempts_exhausted"
    me = client.get(f"{API}/today").json()["me"]
    assert me["attempts_used"] == 3 and me["best_score"] == max(scores) and [a["score"] for a in me["attempts"]] == scores
    board = client.get(f"{API}/leaderboard").json()
    assert board["participants"] == 1 and board["entries"][0]["score"] == max(scores)


def test_attempts_reset_with_the_new_day(client, make_user, clock):
    make_user()
    for _ in range(3):
        submit(client, [[[10, 10], [245, 245]]])
    assert submit(client, [[[10, 10], [245, 245]]]).status_code == 409
    clock.advance(days=1)
    assert client.get(f"{API}/today").json()["me"]["attempts_used"] == 0
    assert submit(client, [[[10, 10], [245, 245]]]).status_code == 200


def test_automated_looking_attempts_are_kept_but_not_counted(client, make_user):
    make_user()
    target = client.get(f"{API}/today").json()["target"]
    fast = submit(client, strokes_of(target)[0], ms=40).json()                # 40 ms: not a human
    assert fast["counted"] is False and fast["rank"] is None and fast["best_score"] is None
    assert submit(client, strokes_of(target)[1], ms=None).json()["counted"] is False
    board = client.get(f"{API}/leaderboard").json()
    assert board["participants"] == 0 and board["entries"] == []
    today = client.get(f"{API}/today").json()["me"]
    assert today["attempts_used"] == 2 and today["best_score"] is None        # they still used up attempts


def test_input_limits_apply_to_attempts(client, make_user):
    make_user()
    assert client.post(f"{API}/attempts", json={"strokes": [[[10, 400], [20, 20]]], "duration_ms": 3000}).status_code == 422
    assert client.post(f"{API}/attempts", json={"strokes": [], "duration_ms": 3000}).status_code == 422


# ---------------------------------------------------------------- leaderboard rules

def test_ranking_by_best_score_then_earliest_and_one_row_per_player(app, client):
    day = T0.date()
    client.get(f"{API}/today")
    (_, a), (_, b), (_, c), (_, d) = [new_player(app, n) for n in ("Ann", "Bob", "Cy", "Di")]
    add_attempt(app, a, day, 60, minutes=1)
    add_attempt(app, b, day, 90, minutes=2)
    add_attempt(app, b, day, 40, minutes=3, no=2)                              # a worse later attempt must not replace the best
    add_attempt(app, c, day, 60, minutes=0)                                    # ties Ann on score but got there first
    add_attempt(app, d, day, 100, minutes=4, suspect=True)                     # flagged: invisible
    board = client.get(f"{API}/leaderboard").json()
    assert board["participants"] == 3
    assert [(e["rank"], e["name"], e["score"]) for e in board["entries"]] == [(1, "Bob", 90), (2, "Cy", 60), (3, "Ann", 60)]


def test_viewer_is_marked_and_ranked_even_outside_the_top_list(app, client):
    day = T0.date()
    client.get(f"{API}/today")
    players = [new_player(app, f"P{i}") for i in range(5)]
    for i, (_, uid) in enumerate(players):
        add_attempt(app, uid, day, 100 - i * 10, minutes=i)                   # P0=100 ... P4=60
    last_client = players[4][0]
    board = last_client.get(f"{API}/leaderboard", params={"limit": 2}).json()
    assert [e["name"] for e in board["entries"]] == ["P0", "P1"] and board["participants"] == 5
    assert board["me"] == {"rank": 5, "name": "P4", "score": 60, "recognised_at": board["me"]["recognised_at"], "is_me": True}
    top = players[0][0].get(f"{API}/leaderboard", params={"limit": 2}).json()
    assert top["entries"][0]["is_me"] is True and top["me"]["rank"] == 1
    assert client.get(f"{API}/leaderboard", params={"limit": 2}).json()["me"] is None        # a visitor has no row


def test_players_can_hide_their_name_but_keep_their_rank(app, client):
    day = T0.date()
    client.get(f"{API}/today")
    (_, a), (ghost, g) = new_player(app, "Visible Vi"), new_player(app, "Secret Sam", show=False)
    add_attempt(app, g, day, 95, minutes=1)
    add_attempt(app, a, day, 50, minutes=2)
    board = client.get(f"{API}/leaderboard").json()
    assert [(e["rank"], e["name"]) for e in board["entries"]] == [(1, "Anonymous"), (2, "Visible Vi")]
    assert "Secret" not in json.dumps(board)
    assert ghost.get(f"{API}/leaderboard").json()["me"]["name"] == "Anonymous"             # even their own row follows their choice
    assert ghost.get("/api/v1/auth/session").json()["user"]["show_on_leaderboard"] is False


def test_leaderboard_never_exposes_emails_or_ids(app, client):
    client.get(f"{API}/today")
    _, uid = new_player(app, "Eve")
    add_attempt(app, uid, T0.date(), 80)
    text = json.dumps(client.get(f"{API}/leaderboard").json())
    assert "example.com" not in text and "user_id" not in text and "email" not in text
    assert set(client.get(f"{API}/leaderboard").json()["entries"][0]) == {"rank", "name", "score", "recognised_at", "is_me"}


def test_leaderboard_for_past_days_and_invalid_days(app, client, clock):
    client.get(f"{API}/today")
    _, uid = new_player(app, "Old Timer")
    add_attempt(app, uid, T0.date(), 70)
    clock.advance(days=2)
    yesterday = client.get(f"{API}/leaderboard", params={"day": "2026-10-03"}).json()
    assert yesterday["day"] == "2026-10-03" and yesterday["entries"][0]["name"] == "Old Timer"
    assert client.get(f"{API}/leaderboard", params={"day": "2026-10-04"}).status_code == 404       # nobody opened the app that day
    assert client.get(f"{API}/leaderboard", params={"day": "2030-01-01"}).json()["error"]["code"] == "future_day"
    assert client.get(f"{API}/leaderboard", params={"day": "not-a-date"}).status_code == 422
    assert client.get(f"{API}/leaderboard").json()["participants"] == 0                        # today is a fresh board


# ---------------------------------------------------------------- personal challenge stats

def test_challenge_stats_and_streaks(app, client, clock, make_user):
    user = make_user()
    for offset, score in [(0, 80), (1, 55), (2, 95), (4, 30)]:                  # played today, yesterday, 2 days ago, and 4 days ago (gap)
        day = (clock.now - timedelta(days=offset)).date()
        with app.state.session_factory() as db:
            from app.models import DailyChallenge
            db.add(DailyChallenge(day=day, target="cat", model_version="v1"))
            db.commit()
        add_attempt(app, user["id"], day, score)
        if offset == 0:
            add_attempt(app, user["id"], day, 10, no=2)                          # a worse second attempt that day
    add_attempt(app, user["id"], (clock.now - timedelta(days=3)).date(), 100, suspect=True)         # flagged day does not extend the streak
    s = client.get(f"{API}/me").json()
    assert s["played"] == 4 and s["best_score"] == 95 and s["average_best"] == round((80 + 55 + 95 + 30) / 4, 1)
    assert s["streak"] == {"current": 3, "longest": 3}
    assert [(h["day"], h["best_score"]) for h in s["history"]] == [("2026-10-03", 80), ("2026-10-02", 55), ("2026-10-01", 95), ("2026-09-29", 30)]
    assert client.get(f"{API}/me").status_code == 200
    assert TestClient(app).get(f"{API}/me").status_code == 401


def test_deleting_an_account_removes_its_attempts_from_the_board(app, client):
    client.get(f"{API}/today")
    leaver, uid = new_player(app, "Leaver")
    add_attempt(app, uid, T0.date(), 99)
    assert client.get(f"{API}/leaderboard").json()["participants"] == 1
    assert leaver.request("DELETE", "/api/v1/me", json={"password": PASSWORD}).status_code == 204
    assert client.get(f"{API}/leaderboard").json()["participants"] == 0


def test_scoring_reports_a_clear_error_when_the_model_is_missing(tmp_path, clock):
    with TestClient(create_app(make_settings(models_dir=tmp_path), clock=clock)) as c:
        r = c.get(f"{API}/today")
        assert r.status_code == 503 and r.json()["error"]["code"] == "model_unavailable"
