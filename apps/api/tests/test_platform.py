import hashlib
import json
from pathlib import Path
from datetime import date, timedelta

from fastapi.testclient import TestClient
from sqlalchemy import func, select

from app.cli import main as cli_main, set_admin
from app.config import get_settings
from app.main import create_app
from app.models import ApiKey, ApiUsage, User
from app.services.metering import daily_series
from tests.conftest import PASSWORD, REPO_MODELS, SAMPLES, build_app, make_settings, strokes_of

API = "/api/v1"
TRIANGLE = [[[20, 200], [128, 40], [236, 200], [20, 200]]]            # the example payload used in the developer docs


def register(c, email, name):
    r = c.post(f"{API}/auth/register", json={"email": email, "password": PASSWORD, "display_name": name})
    assert r.status_code == 201, r.text
    return r.json()


def create_key(c, name="backend"):
    r = c.post(f"{API}/keys", json={"name": name})
    assert r.status_code == 201, r.text
    return r.json()


def call(app, key, strokes=TRIANGLE, header="bearer", **body):
    """A server-to-server call: no cookies, no Origin header."""
    headers = {"Authorization": f"Bearer {key}"} if header == "bearer" else {"X-API-Key": key}
    return TestClient(app).post(f"{API}/predict", json={"strokes": strokes, **body}, headers=headers)


# ---------------------------------------------------------------- key lifecycle

def test_a_key_is_shown_once_and_only_its_hash_is_stored(client, make_user):
    make_user()
    k = create_key(client)
    assert k["key"].startswith("prs_sk_") and k["prefix"] == k["key"][:11] and k["used_today"] == 0 and k["daily_limit"] == 1000
    listed = client.get(f"{API}/keys").json()
    assert [x["id"] for x in listed] == [k["id"]] and "key" not in listed[0] and "key_hash" not in listed[0]
    with client.app.state.session_factory() as db:
        row = db.scalar(select(ApiKey))
        assert row.key_hash == hashlib.sha256(k["key"].encode()).hexdigest() and k["key"] not in json.dumps(row.__dict__, default=str)


def test_keys_need_a_session_and_belong_to_their_owner(client, other_client, make_user):
    assert client.get(f"{API}/keys").status_code == 401
    make_user("a@example.com")
    k = create_key(client)
    register(other_client, "b@example.com", "Bea")
    assert other_client.get(f"{API}/keys").json() == []
    assert other_client.delete(f"{API}/keys/{k['id']}").status_code == 404
    assert other_client.get(f"{API}/keys/{k['id']}/usage").status_code == 404


def test_active_key_limit_and_revocation_frees_a_slot(clock, scorer):
    with TestClient(build_app(clock, scorer, max_keys_per_user=2)) as c:
        register(c, "a@example.com", "Ada")
        first, _ = create_key(c, "one"), create_key(c, "two")
        over = c.post(f"{API}/keys", json={"name": "three"})
        assert over.status_code == 409 and over.json()["error"]["code"] == "key_limit"
        assert c.delete(f"{API}/keys/{first['id']}").status_code == 204
        assert c.post(f"{API}/keys", json={"name": "three"}).status_code == 201


def test_key_names_are_validated(client, make_user):
    make_user()
    assert client.post(f"{API}/keys", json={"name": "   "}).status_code == 422
    assert client.post(f"{API}/keys", json={"name": "x" * 61}).status_code == 422


# ---------------------------------------------------------------- predictions

def test_predict_returns_ranked_guesses_and_quota_headers(app, client, make_user):
    make_user()
    key = create_key(client)["key"]
    r = call(app, key)
    assert r.status_code == 200, r.text
    body = r.json()
    probs = [g["probability"] for g in body["predictions"]]
    assert body["model"] == "v1" and len(probs) == 5 and probs == sorted(probs, reverse=True) and 0 < sum(probs) <= 1.0001
    assert all(g["label"] in app.state.scorer.classes for g in body["predictions"]) and body["ink"] > 0 and body["inference_ms"] > 0
    assert (r.headers["RateLimit-Limit"], r.headers["RateLimit-Remaining"], r.headers["RateLimit-Reset"]) == ("1000", "999", str(12 * 3600))


def test_top_k_is_honoured_and_bounded(app, client, make_user):
    make_user()
    key = create_key(client)["key"]
    assert [len(call(app, key, top_k=k).json()["predictions"]) for k in (1, 3, 10)] == [1, 3, 10]
    assert call(app, key, top_k=0).status_code == 422 and call(app, key, top_k=11).status_code == 422


def test_both_header_styles_work(app, client, make_user):
    make_user()
    key = create_key(client)["key"]
    assert call(app, key, header="bearer").status_code == 200 and call(app, key, header="x-api-key").status_code == 200


def test_the_api_recognises_real_held_out_sketches(clock, scorer):
    """End to end through the public API: one real sketch per class, finished drawing."""
    app = build_app(clock, scorer, api_per_minute=1000, api_daily_limit=10_000)
    with TestClient(app) as c:
        register(c, "a@example.com", "Ada")
        key = create_key(c)["key"]
        labels = sorted({s["label"] for s in SAMPLES})
        hits = sum(call(app, key, strokes_of(lab)[0], top_k=1).json()["predictions"][0]["label"] == lab for lab in labels)
        assert hits / len(labels) >= 0.75, f"{hits}/{len(labels)}"


def test_bad_keys_are_all_refused_the_same_way(app, client, make_user):
    make_user()
    good = create_key(client)
    bodies = []
    for attempt in (None, "nonsense", "prs_sk_" + "a" * 32, good["key"][:-1] + ("A" if good["key"][-1] != "A" else "B")):
        headers = {"Authorization": f"Bearer {attempt}"} if attempt else {}
        r = TestClient(app).post(f"{API}/predict", json={"strokes": TRIANGLE}, headers=headers)
        assert r.status_code == 401 and r.json()["error"]["code"] == "invalid_api_key"
        bodies.append(r.json())
    assert all(b == bodies[0] for b in bodies)                                  # no hint about which part was wrong


def test_revoking_a_key_stops_it_immediately(app, client, make_user):
    make_user()
    k = create_key(client)
    assert call(app, k["key"]).status_code == 200
    assert client.delete(f"{API}/keys/{k['id']}").status_code == 204
    assert call(app, k["key"]).status_code == 401
    assert client.get(f"{API}/keys").json()[0]["revoked_at"] is not None
    assert client.delete(f"{API}/keys/{k['id']}").status_code == 204             # revoking twice is harmless


def test_secret_keys_are_refused_from_browsers(app, client, make_user):
    make_user()
    key = create_key(client)["key"]
    r = TestClient(app).post(f"{API}/predict", json={"strokes": TRIANGLE}, headers={"Authorization": f"Bearer {key}", "Origin": "https://evil.example"})
    assert r.status_code == 403 and r.json()["error"]["code"] == "browser_not_allowed"
    assert "access-control-allow-origin" not in r.headers


def test_sessions_and_keys_are_not_interchangeable(app, client, make_user):
    make_user()
    key = create_key(client)["key"]
    assert TestClient(app).get(f"{API}/me", headers={"Authorization": f"Bearer {key}"}).status_code == 401       # a key is not a login
    assert client.post(f"{API}/predict", json={"strokes": TRIANGLE}).status_code == 401                         # a login is not a key


def test_burst_limit_per_key(clock, scorer):
    app = build_app(clock, scorer, api_per_minute=3)
    with TestClient(app) as c:
        register(c, "a@example.com", "Ada")
        key = create_key(c)["key"]
        codes = [call(app, key).status_code for _ in range(5)]
        assert codes == [200, 200, 200, 429, 429]
        limited = call(app, key)
        assert limited.json()["error"]["code"] == "rate_limited" and int(limited.headers["Retry-After"]) >= 1


def test_daily_quota_resets_at_midnight_utc(clock, scorer):
    app = build_app(clock, scorer, api_daily_limit=2)
    with TestClient(app) as c:
        register(c, "a@example.com", "Ada")
        key = create_key(c)["key"]
        assert [call(app, key).status_code for _ in range(3)] == [200, 200, 429]
        over = call(app, key)
        assert over.json()["error"]["code"] == "quota_exceeded" and over.headers["Retry-After"] == str(12 * 3600)
        clock.advance(hours=13)                                                  # past midnight UTC
        assert call(app, key).status_code == 200


# ---------------------------------------------------------------- metering

def test_usage_counts_every_call_including_failures(clock, scorer):
    app = build_app(clock, scorer, max_points=5)
    with TestClient(app) as c:
        register(c, "a@example.com", "Ada")
        k = create_key(c)
        assert call(app, k["key"]).status_code == 200 and call(app, k["key"]).status_code == 200
        too_big = call(app, k["key"], strokes=[[[i, i] for i in range(10)]])
        assert too_big.status_code == 422 and too_big.json()["error"]["code"] == "too_complex"
        usage = c.get(f"{API}/keys/{k['id']}/usage").json()
        assert len(usage) == 14 and usage[-1]["day"] == "2026-10-03"
        assert (usage[-1]["requests"], usage[-1]["errors"]) == (3, 1) and usage[-1]["avg_ms"] > 0
        assert all(d["requests"] == 0 and d["avg_ms"] is None for d in usage[:-1])             # zero-filled, nothing invented
        listed = c.get(f"{API}/keys").json()[0]
        assert listed["used_today"] == 3 and listed["last_used_at"] is not None
        assert c.get(f"{API}/keys/{k['id']}/usage", params={"days": 91}).status_code == 422


def test_failed_authentication_is_not_metered(app, client, make_user):
    make_user()
    k = create_key(client)
    TestClient(app).post(f"{API}/predict", json={"strokes": TRIANGLE}, headers={"Authorization": "Bearer prs_sk_" + "z" * 32})
    assert client.get(f"{API}/keys").json()[0]["used_today"] == 0 and k["used_today"] == 0


def test_daily_series_aggregates_several_keys_and_fills_gaps(app, client, make_user):
    user = make_user()
    a, b = create_key(client, "a"), create_key(client, "b")
    today = date(2026, 10, 3)
    with app.state.session_factory() as db:
        db.add_all([ApiUsage(key_id=a["id"], day=today, requests=4, errors=1, total_ms=40.0),
                    ApiUsage(key_id=b["id"], day=today, requests=6, errors=0, total_ms=30.0),
                    ApiUsage(key_id=a["id"], day=today - timedelta(days=2), requests=10, errors=2, total_ms=100.0)])
        db.commit()
        series = daily_series(db, [a["id"], b["id"]], today, 4)
    assert [d["requests"] for d in series] == [0, 10, 0, 10] and series[-1]["errors"] == 1 and series[-1]["avg_ms"] == 7.0
    assert user["id"]


# ---------------------------------------------------------------- model info, admin, CLI

def test_model_info_is_public(client):
    meta = json.loads((REPO_MODELS / "v1" / "meta.json").read_text(encoding="utf-8"))
    r = client.get(f"{API}/model")
    s = client.app.state.settings
    assert r.status_code == 200 and r.json() == {"version": "v1", "classes": meta["classes"], "limits": {
        "requests_per_minute": s.api_per_minute, "requests_per_day": s.api_daily_limit, "max_strokes": s.max_strokes,
        "max_points": s.max_points, "max_active_keys": s.max_keys_per_user, "top_k_max": 10}}


def documented_example() -> dict:
    """The example response exactly as written in the developer docs source (apps/web/src/features/developers/docsExamples.ts)."""
    import re

    text = (Path(__file__).resolve().parents[3] / "apps" / "web" / "src" / "features" / "developers" / "docsExamples.ts").read_text(encoding="utf-8")
    block = text[text.index("EXAMPLE_RESPONSE"):]
    return {"model": re.search(r'model: "(v\d+)"', block).group(1), "ink": float(re.search(r"ink: ([\d.]+)", block).group(1)),
            "predictions": [(m.group(1), float(m.group(2))) for m in re.finditer(r'label: "([^"]+)", probability: ([\d.]+)', block)]}


def test_the_documented_example_is_what_the_api_really_returns(clock, live_scorer):
    """The developer docs show a request and response captured from the real model. This reads the docs file and compares it with the model that is
    LIVE in models/registry.json: promoting a new version fails this test until the example is captured again, so the docs cannot go stale quietly."""
    doc = documented_example()
    app = build_app(clock, live_scorer)
    with TestClient(app) as c:
        register(c, "doc@example.com", "Doc")
        key = create_key(c)["key"]
        body = call(app, key, TRIANGLE, top_k=3).json()
    assert body["model"] == doc["model"], f"the docs show model {doc['model']} but {body['model']} is live: recapture the example in docsExamples.ts"
    assert [g["label"] for g in body["predictions"]] == [label for label, _ in doc["predictions"]]
    for got, (_, want) in zip(body["predictions"], doc["predictions"]):
        assert abs(got["probability"] - want) < 0.01, (got, want)
    assert body["ink"] == doc["ink"]


def test_admin_metrics_are_for_admins_and_match_the_data(app, client, other_client, make_user):
    assert client.get(f"{API}/admin/metrics").status_code == 401
    make_user("boss@example.com", "Boss")
    assert client.get(f"{API}/admin/metrics").status_code == 403                   # signing up never makes you an admin
    with app.state.session_factory() as db:
        assert set_admin(db, "boss@example.com", True)

    register(other_client, "dev@example.com", "Dana Dev")
    key = create_key(other_client, "production")
    for _ in range(2):
        assert call(app, key["key"]).status_code == 200
    drawing = {"strokes": TRIANGLE, "label": "star", "ai_guess": "star", "ai_confidence": 0.9, "recognised_at": 0.3, "model_version": "v1"}
    assert other_client.post(f"{API}/drawings", json=drawing).status_code == 201

    m = client.get(f"{API}/admin/metrics").json()
    assert (m["users"]["total"], m["users"]["last_7_days"]) == (2, 2) and (m["drawings"]["total"], m["drawings"]["last_7_days"]) == (1, 1)
    assert m["api"]["active_keys"] == 1 and m["api"]["requests_today"] == 2 and m["api"]["requests_7d"] == 2 and m["api"]["errors_7d"] == 0
    assert m["api"]["avg_ms_7d"] > 0 and len(m["api"]["daily"]) == 14 and m["api"]["daily"][-1]["requests"] == 2
    assert m["api"]["top_keys"] == [{"prefix": key["prefix"], "name": "production", "owner": "Dana Dev", "requests_7d": 2}]
    assert m["challenge_today"] == {"players": 0, "attempts": 0, "flagged": 0}
    assert m["model_version"] == "v1" and m["model_loaded"] is True
    assert "example.com" not in json.dumps(m)                                       # owners are names, never emails


def test_set_admin_helper(app, client, make_user):
    make_user("a@example.com", "Ada")
    with app.state.session_factory() as db:
        assert set_admin(db, " A@Example.com ", True) and db.scalar(select(User.is_admin)) is True
        assert set_admin(db, "a@example.com", False) and db.scalar(select(User.is_admin)) is False
        assert set_admin(db, "nobody@example.com", True) is False


def test_cli_promotes_by_email(tmp_path, monkeypatch, capsys):
    url = f"sqlite:///{(tmp_path / 'cli.db').as_posix()}"
    with TestClient(create_app(make_settings(env="dev", database_url=url))) as c:               # dev mode runs the migrations on this file
        register(c, "ops@example.com", "Ops")
    monkeypatch.setenv("PRESCRIBBLE_DATABASE_URL", url)
    get_settings.cache_clear()
    try:
        assert cli_main(["make-admin", "ops@example.com"]) == 0 and "now an admin" in capsys.readouterr().out
        assert cli_main(["make-admin", "ghost@example.com"]) == 1 and "No account" in capsys.readouterr().err
        assert cli_main(["remove-admin", "ops@example.com"]) == 0
    finally:
        get_settings.cache_clear()


def test_deleting_an_account_removes_its_keys_and_usage(app, client, make_user):
    make_user()
    k = create_key(client)
    assert call(app, k["key"]).status_code == 200
    assert client.request("DELETE", f"{API}/me", json={"password": PASSWORD}).status_code == 204
    with app.state.session_factory() as db:
        assert db.scalar(select(func.count(ApiKey.id))) == 0 and db.scalar(select(func.count(ApiUsage.id))) == 0
    assert call(app, k["key"]).status_code == 401
