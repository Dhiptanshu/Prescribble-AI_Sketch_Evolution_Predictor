from fastapi.testclient import TestClient

from app.main import create_app
from tests.conftest import PASSWORD, make_settings

REG = "/api/v1/auth/register"
LOGIN = "/api/v1/auth/login"
ME = "/api/v1/me"


def test_register_sets_httponly_cookie_and_returns_user(client):
    r = client.post(REG, json={"email": "Ada@Example.com ", "password": PASSWORD, "display_name": "  Ada   L  "})
    assert r.status_code == 201
    body = r.json()
    assert body["email"] == "ada@example.com" and body["display_name"] == "Ada L"
    assert body["is_admin"] is False and body["consent_training"] is False
    assert "password" not in str(body)
    cookie = r.headers["set-cookie"].lower()
    assert "httponly" in cookie and "samesite=lax" in cookie


def test_me_requires_authentication(client):
    r = client.get(ME)
    assert r.status_code == 401 and r.json()["error"]["code"] == "unauthenticated"


def test_register_then_me_then_logout(client, make_user):
    user = make_user()
    assert client.get(ME).json()["id"] == user["id"]
    assert client.post("/api/v1/auth/logout").status_code == 204
    assert client.get(ME).status_code == 401


def test_duplicate_email_is_rejected_case_insensitively(client, make_user):
    make_user("ada@example.com")
    r = client.post(REG, json={"email": "ADA@example.com", "password": PASSWORD, "display_name": "Other"})
    assert r.status_code == 409 and r.json()["error"]["code"] == "email_taken"


def test_validation_errors_use_the_standard_shape(client):
    r = client.post(REG, json={"email": "not-an-email", "password": "short", "display_name": " "})
    assert r.status_code == 422
    err = r.json()["error"]
    assert err["code"] == "validation_error"
    assert {d["field"] for d in err["details"]} == {"email", "password", "display_name"}


def test_login_success_and_failures_are_indistinguishable(client, make_user):
    make_user()
    client.post("/api/v1/auth/logout")
    ok = client.post(LOGIN, json={"email": "ada@example.com", "password": PASSWORD})
    assert ok.status_code == 200 and client.get(ME).status_code == 200
    client.post("/api/v1/auth/logout")
    wrong_pw = client.post(LOGIN, json={"email": "ada@example.com", "password": "nope-nope-nope"})
    unknown = client.post(LOGIN, json={"email": "ghost@example.com", "password": PASSWORD})
    assert wrong_pw.status_code == unknown.status_code == 401
    assert wrong_pw.json() == unknown.json()


def test_tampered_or_foreign_token_is_rejected(client, make_user):
    make_user()
    client.cookies.set("prescribble_session", "garbage.token.value")
    assert client.get(ME).status_code == 401


def test_bearer_token_works_for_scripts(client, make_user):
    make_user()
    token = client.cookies.get("prescribble_session")
    with TestClient(client.app) as other:
        r = other.get(ME, headers={"Authorization": f"Bearer {token}"})
        assert r.status_code == 200 and r.json()["email"] == "ada@example.com"


def test_profile_update_and_consent_is_opt_in(client, make_user):
    make_user()
    assert client.get(ME).json()["consent_training"] is False
    r = client.patch(ME, json={"display_name": "Countess", "consent_training": True})
    assert r.status_code == 200 and r.json()["display_name"] == "Countess" and r.json()["consent_training"] is True
    assert client.patch(ME, json={"display_name": ""}).status_code == 422


def test_export_contains_the_users_data(client, make_user):
    make_user()
    data = client.get("/api/v1/me/export").json()
    assert data["user"]["email"] == "ada@example.com" and data["drawings"] == []


def test_delete_account_requires_password_and_removes_user(client, make_user):
    make_user()
    bad = client.request("DELETE", ME, json={"password": "wrong-password"})
    assert bad.status_code == 403
    ok = client.request("DELETE", ME, json={"password": PASSWORD})
    assert ok.status_code == 204
    assert client.get(ME).status_code == 401
    assert client.post(LOGIN, json={"email": "ada@example.com", "password": PASSWORD}).status_code == 401


def test_auth_endpoints_are_rate_limited():
    with TestClient(create_app(make_settings(auth_attempts_per_minute=3))) as c:
        codes = [c.post(LOGIN, json={"email": "x@example.com", "password": "whatever1"}).status_code for _ in range(5)]
    assert codes[:3] == [401, 401, 401] and codes[3:] == [429, 429]


def test_unknown_route_uses_standard_error_shape(client):
    r = client.get("/api/v1/nope")
    assert r.status_code == 404 and r.json()["error"]["code"] == "not_found"


def test_healthz_checks_the_database(client):
    r = client.get("/healthz")
    assert r.status_code == 200 and r.json() == {"status": "ok"}
    assert "x-request-id" in r.headers


def test_prod_requires_a_strong_secret():
    import pytest
    with pytest.raises(ValueError):
        make_settings(env="prod", secret_key="short")


def test_session_endpoint_never_returns_401(client, make_user):
    assert client.get("/api/v1/auth/session").json() == {"user": None}      # visitor: 200, no console error
    user = make_user()
    body = client.get("/api/v1/auth/session")
    assert body.status_code == 200 and body.json()["user"]["id"] == user["id"]
    client.post("/api/v1/auth/logout")
    assert client.get("/api/v1/auth/session").json() == {"user": None}
