"""Security hardening: response headers, the content security policy, the body cap for chunked uploads and the cross-site write check."""
import pytest
from fastapi.testclient import TestClient

from app.middleware import CONTENT_SECURITY_POLICY
from tests.conftest import PASSWORD, build_app

API = "/api/v1"
SQUARE = [[[20, 20], [200, 25], [205, 190], [25, 200], [20, 20]]]
DRAWING = {"strokes": SQUARE, "label": "house", "ai_guess": "house", "ai_confidence": 0.9, "model_version": "v1"}


@pytest.fixture
def dist(tmp_path):
    (tmp_path / "models" / "v1").mkdir(parents=True)
    (tmp_path / "index.html").write_text("<html><body>app</body></html>")
    (tmp_path / "page.html").write_text("<html></html>")
    (tmp_path / "app.js").write_text("x")
    return tmp_path


# ---------------------------------------------------------------- headers

def test_every_response_carries_the_basic_security_headers(client):
    for response in (client.get("/healthz"), client.get(f"{API}/auth/session"), client.get(f"{API}/nothing-here")):          # success, JSON and error
        h = response.headers
        assert h["x-content-type-options"] == "nosniff" and h["x-frame-options"] == "DENY"
        assert h["referrer-policy"] == "strict-origin-when-cross-origin" and "camera=()" in h["permissions-policy"]
        assert "strict-transport-security" not in h                                                                      # plain-http development


def test_hsts_is_on_only_for_https_only_deployments(clock, scorer):
    with TestClient(build_app(clock, scorer, cookie_secure=True)) as c:
        assert "max-age=" in c.get("/healthz").headers["strict-transport-security"]


def test_the_content_security_policy_is_on_html_only_and_not_on_the_api_docs(clock, scorer, dist):
    with TestClient(build_app(clock, scorer, web_dist=dist)) as c:
        index, page, deep = c.get("/"), c.get("/page.html"), c.get("/some/client/route")
        for r in (index, page, deep):
            assert r.headers["content-security-policy"] == CONTENT_SECURITY_POLICY
        assert "content-security-policy" not in c.get("/app.js").headers and "content-security-policy" not in c.get("/healthz").headers
        assert "content-security-policy" not in c.get("/api/docs").headers                                               # its viewer loads from a CDN


def test_the_policy_allows_what_the_app_needs_and_nothing_extra():
    csp = dict(part.strip().split(" ", 1) for part in CONTENT_SECURITY_POLICY.split(";"))
    assert csp["default-src"] == "'self'" and csp["object-src"] == "'none'" and csp["frame-ancestors"] == "'none'" and csp["base-uri"] == "'self'"
    assert "'wasm-unsafe-eval'" in csp["script-src"] and "'unsafe-eval'" not in csp["script-src"] and "http" not in csp["script-src"]      # WebAssembly yes, eval no, no other hosts
    assert "ws:" in csp["connect-src"] and "wss:" in csp["connect-src"]                                                  # the live classroom socket


# ---------------------------------------------------------------- body cap

def chunks(total: int, size: int = 100_000):
    def generate():
        sent = 0
        while sent < total:
            yield b"x" * min(size, total - sent)
            sent += size
    return generate()


def test_a_chunked_upload_without_a_length_is_still_capped(client, make_user):
    make_user()
    r = client.post(f"{API}/drawings", content=chunks(2_500_000), headers={"Content-Type": "application/json"})
    assert r.status_code == 413 and r.json()["error"]["code"] == "payload_too_large"
    assert "x-content-type-options" in r.headers


def test_an_oversized_content_length_is_refused_before_reading(client, make_user):
    make_user()
    r = client.post(f"{API}/drawings", content=b"{" + b" " * 1_100_000 + b"}", headers={"Content-Type": "application/json"})
    assert r.status_code == 413


def test_a_normal_request_passes_the_cap(client, make_user):
    make_user()
    assert client.post(f"{API}/drawings", json=DRAWING).status_code == 201


# ---------------------------------------------------------------- cross-site writes

def test_a_cookie_write_from_another_site_is_refused(client, make_user):
    make_user()
    r = client.post(f"{API}/drawings", json=DRAWING, headers={"Origin": "https://evil.example"})
    assert r.status_code == 403 and r.json()["error"]["code"] == "bad_origin"
    assert client.get(f"{API}/drawings").json()["items"] == []                                                           # nothing was written


def test_every_kind_of_write_is_covered_including_account_deletion(client, make_user):
    make_user()
    evil = {"Origin": "https://evil.example"}
    assert client.request("DELETE", f"{API}/me", json={"password": PASSWORD}, headers=evil).status_code == 403
    assert client.patch(f"{API}/me", json={"display_name": "Hacked"}, headers=evil).status_code == 403
    assert client.post(f"{API}/rooms", json={"name": "x"}, headers=evil).status_code == 403
    assert client.get(f"{API}/auth/session").json()["user"]["display_name"] == "Ada"                                     # still signed in and unchanged


def test_the_sites_own_origin_and_listed_origins_are_allowed(client, make_user):
    make_user()
    assert client.post(f"{API}/drawings", json=DRAWING, headers={"Origin": "http://testserver"}).status_code == 201      # same host
    assert client.post(f"{API}/drawings", json={**DRAWING, "strokes": [[[1, 1], [9, 9]]]}, headers={"Origin": "http://localhost:5173"}).status_code == 201  # dev server


def test_a_trusted_origin_can_be_added_for_a_proxy_that_rewrites_host(clock, scorer):
    app = build_app(clock, scorer, trusted_origins=["https://prescribble.example"])
    with TestClient(app) as c:
        assert c.post(f"{API}/auth/register", json={"email": "p@example.com", "password": PASSWORD, "display_name": "P"}).status_code == 201
        assert c.post(f"{API}/drawings", json=DRAWING, headers={"Origin": "https://prescribble.example"}).status_code == 201


def test_a_forwarded_host_counts_as_the_same_site(client, make_user):
    make_user()
    r = client.post(f"{API}/drawings", json=DRAWING, headers={"Origin": "https://real.example", "X-Forwarded-Host": "real.example"})
    assert r.status_code == 201


def test_requests_without_the_session_cookie_are_not_blocked_by_origin(other_client):
    """Visitors and students (no cookie) use room codes and tokens, not an ambient credential, so a different origin is fine."""
    r = other_client.post(f"{API}/rooms/join", json={"code": "ZZZZZZ", "nickname": "a"}, headers={"Origin": "https://some-school.example"})
    assert r.status_code == 404 and r.json()["error"]["code"] == "room_not_found"


def test_a_form_post_with_the_cookie_is_not_treated_as_json(client, make_user):
    make_user()
    r = client.post(f"{API}/drawings", content="label=house", headers={"Content-Type": "application/x-www-form-urlencoded"})
    assert r.status_code == 422 and client.get(f"{API}/drawings").json()["items"] == []
