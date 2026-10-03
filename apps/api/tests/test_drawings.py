import pytest
from fastapi.testclient import TestClient

from app.main import create_app
from tests.conftest import PASSWORD, make_settings

URL = "/api/v1/drawings"
SQUARE = [[[60, 60], [200, 60], [200, 200], [60, 200], [60, 60]]]          # perimeter 560


def payload(**over):
    base = dict(strokes=SQUARE, label="house", ai_guess="house", ai_confidence=0.93, recognised_at=0.25, model_version="v1", duration_ms=4200)
    return {**base, **over}


def register(c, email, name="User"):
    r = c.post("/api/v1/auth/register", json={"email": email, "password": PASSWORD, "display_name": name})
    assert r.status_code == 201, r.text
    return r.json()


def test_saving_requires_sign_in(client):
    assert client.post(URL, json=payload()).status_code == 401
    assert client.get(URL).status_code == 401


def test_create_computes_derived_fields_on_the_server(client, make_user):
    make_user()
    r = client.post(URL, json={**payload(), "n_strokes": 999, "ink": 1, "user_id": 42, "share_token": "hacked-token"})
    assert r.status_code == 201
    d = r.json()
    assert d["n_strokes"] == 1 and d["ink"] == 560.0                       # recomputed, client values ignored
    assert d["share_token"] is None and d["label"] == "house" and d["mode"] == "free"
    stored = client.get(f"{URL}/{d['id']}").json()["strokes"]
    assert stored == [[[60.0, 60.0], [200.0, 60.0], [200.0, 200.0], [60.0, 200.0], [60.0, 60.0]]]


def test_rejects_coordinates_outside_the_frame(client, make_user):
    make_user()
    r = client.post(URL, json=payload(strokes=[[[10, 10], [300, 20]]]))
    assert r.status_code == 422 and r.json()["error"]["code"] == "validation_error"


def test_rejects_empty_drawings(client, make_user):
    make_user()
    assert client.post(URL, json=payload(strokes=[])).status_code == 422
    assert client.post(URL, json=payload(strokes=[[]])).status_code == 422


def test_rejects_unknown_classes_using_the_real_model_metadata(client, make_user):
    make_user()
    r = client.post(URL, json=payload(label="spaceship"))
    assert r.status_code == 422 and r.json()["error"]["code"] == "unknown_class"
    assert r.json()["error"]["details"][0]["field"] == "label"
    assert client.post(URL, json=payload(ai_guess="spaceship")).status_code == 422


def test_recognition_time_needs_a_label(client, make_user):
    make_user()
    assert client.post(URL, json=payload(label=None, recognised_at=0.4)).status_code == 422
    assert client.post(URL, json=payload(label=None, recognised_at=None)).status_code == 201


def test_complexity_limits():
    with TestClient(create_app(make_settings(max_points=8, max_strokes=2))) as c:
        register(c, "a@example.com")
        assert c.post(URL, json=payload(strokes=SQUARE)).status_code == 201                       # 5 points
        too_many_points = c.post(URL, json=payload(strokes=SQUARE + SQUARE))                      # 10 points
        assert too_many_points.status_code == 422 and too_many_points.json()["error"]["code"] == "too_complex"
        assert c.post(URL, json=payload(strokes=[[[1, 1]], [[2, 2]], [[3, 3]]])).status_code == 422   # 3 strokes


def test_quota():
    with TestClient(create_app(make_settings(max_drawings_per_user=2))) as c:
        register(c, "a@example.com")
        assert [c.post(URL, json=payload()).status_code for _ in range(3)] == [201, 201, 409]
        assert c.post(URL, json=payload()).json()["error"]["code"] == "quota_exceeded"


def test_list_is_newest_first_and_paginates(client, make_user):
    make_user()
    ids = [client.post(URL, json=payload()).json()["id"] for _ in range(5)]
    first = client.get(URL, params={"limit": 2}).json()
    assert [d["id"] for d in first["items"]] == ids[::-1][:2] and first["next_before"] == first["items"][-1]["id"]
    second = client.get(URL, params={"limit": 2, "before": first["next_before"]}).json()
    assert [d["id"] for d in second["items"]] == ids[::-1][2:4]
    last = client.get(URL, params={"limit": 2, "before": second["next_before"]}).json()
    assert [d["id"] for d in last["items"]] == ids[::-1][4:] and last["next_before"] is None
    assert client.get(URL, params={"limit": 500}).status_code == 422


def test_users_cannot_see_or_change_each_others_drawings(client, other_client, make_user):
    make_user("a@example.com")
    mine = client.post(URL, json=payload()).json()["id"]
    register(other_client, "b@example.com", "Bea")
    assert other_client.get(URL).json() == {"items": [], "next_before": None}
    attempts = [("GET", f"{URL}/{mine}", None), ("PATCH", f"{URL}/{mine}", {"label": "cat"}), ("DELETE", f"{URL}/{mine}", None),
                ("POST", f"{URL}/{mine}/share", None), ("DELETE", f"{URL}/{mine}/share", None)]
    for method, path, body in attempts:
        r = other_client.request(method, path, json=body)
        assert r.status_code == 404, (method, path, r.status_code)                               # 404, not 403: no existence leak
    assert client.get(f"{URL}/{mine}").status_code == 200                                        # untouched


def test_relabel_and_clear(client, make_user):
    make_user()
    d = client.post(URL, json=payload()).json()
    r = client.patch(f"{URL}/{d['id']}", json={"label": "cat"})
    assert r.status_code == 200 and r.json()["label"] == "cat" and r.json()["recognised_at"] == 0.25
    cleared = client.patch(f"{URL}/{d['id']}", json={"label": None}).json()
    assert cleared["label"] is None and cleared["recognised_at"] is None
    assert client.patch(f"{URL}/{d['id']}", json={"label": "spaceship"}).status_code == 422
    assert client.patch(f"{URL}/{d['id']}", json={}).status_code == 422                          # the key is required


def test_delete(client, make_user):
    make_user()
    d = client.post(URL, json=payload()).json()["id"]
    assert client.delete(f"{URL}/{d}").status_code == 204
    assert client.get(f"{URL}/{d}").status_code == 404


def test_sharing_lifecycle(client, other_client, make_user):
    make_user("a@example.com", "Ada")
    d = client.post(URL, json=payload()).json()["id"]
    token = client.post(f"{URL}/{d}/share").json()["token"]
    assert len(token) >= 12 and client.post(f"{URL}/{d}/share").json()["token"] == token         # idempotent
    assert client.get(f"{URL}/{d}").json()["share_token"] == token

    public = other_client.get(f"/api/v1/public/drawings/{token}")                                # no account needed
    assert public.status_code == 200 and public.json()["author"] == "Ada" and public.json()["label"] == "house"
    assert public.headers["cache-control"] == "no-cache"

    assert client.delete(f"{URL}/{d}/share").status_code == 204
    assert other_client.get(f"/api/v1/public/drawings/{token}").status_code == 404               # revoked immediately
    assert client.post(f"{URL}/{d}/share").json()["token"] != token                             # a new link, not the old one


def test_public_page_exposes_only_what_a_share_link_is_for(client, other_client, make_user):
    make_user("secret.person@example.com", "Ada")
    d = client.post(URL, json=payload()).json()["id"]
    token = client.post(f"{URL}/{d}/share").json()["token"]
    r = other_client.get(f"/api/v1/public/drawings/{token}")
    assert set(r.json()) == {"strokes", "label", "ai_guess", "ai_confidence", "recognised_at", "created_at", "model_version", "author"}
    assert "secret.person" not in r.text
    assert other_client.get("/api/v1/public/drawings/not-a-real-token-1").status_code == 404
    assert other_client.get("/api/v1/public/drawings/short").status_code == 422
    assert other_client.get("/api/v1/public/drawings/..%2f..%2fetc").status_code in (404, 422)


def test_export_includes_drawings_and_account_deletion_removes_everything(client, other_client, make_user):
    make_user()
    d = client.post(URL, json=payload()).json()["id"]
    token = client.post(f"{URL}/{d}/share").json()["token"]
    export = client.get("/api/v1/me/export").json()
    assert [x["id"] for x in export["drawings"]] == [d] and export["drawings"][0]["strokes"]

    assert client.request("DELETE", "/api/v1/me", json={"password": PASSWORD}).status_code == 204
    assert other_client.get(f"/api/v1/public/drawings/{token}").status_code == 404               # share link died with the account
    with client.app.state.session_factory() as db:
        from sqlalchemy import func, select

        from app.models import Drawing
        assert db.scalar(select(func.count(Drawing.id))) == 0                                    # cascade, no orphans


def test_writes_are_rate_limited_per_user():
    with TestClient(create_app(make_settings(writes_per_minute=3))) as c:
        register(c, "a@example.com")
        assert [c.post(URL, json=payload()).status_code for _ in range(5)] == [201, 201, 201, 429, 429]
        assert c.get(URL).status_code == 200                                                     # reads are not counted


def test_oversized_bodies_are_refused_before_parsing(client, make_user):
    make_user()
    r = client.post(URL, content=b"x" * 1_100_000, headers={"Content-Type": "application/json"})
    assert r.status_code == 413 and r.json()["error"]["code"] == "payload_too_large"


@pytest.mark.parametrize("path", ["/api/v1/drawings", "/api/v1/me/stats"])
def test_private_endpoints_need_auth(client, path):
    assert client.get(path).status_code == 401
