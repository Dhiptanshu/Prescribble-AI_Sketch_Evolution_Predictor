import pytest
from fastapi.testclient import TestClient

from app.main import create_app
from tests.conftest import make_settings


@pytest.fixture
def web(tmp_path):
    dist = tmp_path / "dist"
    (dist / "assets").mkdir(parents=True)
    (dist / "models" / "v1").mkdir(parents=True)
    (dist / "index.html").write_text("<html>app</html>")
    (dist / "assets" / "app-abc123.js").write_text("console.log(1)")
    (dist / "models" / "v1" / "meta.json").write_text("{}")
    (dist / "ort").mkdir()
    (dist / "ort" / "loader.mjs").write_text("export default 1")
    (dist / "ort" / "runtime.wasm").write_bytes(b"\x00asm")
    (tmp_path / "secret.txt").write_text("outside the web root")
    with TestClient(create_app(make_settings(web_dist=dist))) as c:
        yield c


def test_client_routes_fall_back_to_index(web):
    for path in ("/", "/studio", "/some/deep/route"):
        r = web.get(path)
        assert r.status_code == 200 and "app" in r.text
        assert r.headers["cache-control"] == "no-cache"


def test_assets_and_models_are_served_with_long_cache(web):
    r = web.get("/assets/app-abc123.js")
    assert r.status_code == 200 and "immutable" in r.headers["cache-control"]
    assert web.get("/models/v1/meta.json").status_code == 200
    # fixed-name runtime files must be revalidated, never cached as immutable (a bad response would be stuck for a year)
    assert "immutable" not in web.get("/ort/loader.mjs").headers["cache-control"]


def test_module_scripts_and_wasm_get_browser_safe_media_types(web):
    """Browsers refuse module scripts served as text/plain (the Windows registry default for .mjs)."""
    assert web.get("/ort/loader.mjs").headers["content-type"].startswith("text/javascript")
    assert web.get("/assets/app-abc123.js").headers["content-type"].startswith("text/javascript")
    assert web.get("/ort/runtime.wasm").headers["content-type"] == "application/wasm"


def test_missing_asset_is_a_real_404_not_index(web):
    r = web.get("/assets/missing.js")
    assert r.status_code == 404 and r.json()["error"]["code"] == "not_found"


def test_api_routes_win_and_unknown_api_paths_stay_json_404(web):
    assert web.get("/healthz").json() == {"status": "ok"}
    assert web.get("/api/v1/auth/session").json() == {"user": None}
    r = web.get("/api/v1/does-not-exist")
    assert r.status_code == 404 and r.json()["error"]["code"] == "not_found"


def test_path_traversal_cannot_leave_the_web_root(web):
    for evil in ("/../secret.txt", "/%2e%2e/secret.txt", "/assets/../../secret.txt"):
        r = web.get(evil)
        assert "outside the web root" not in r.text


def test_missing_dist_fails_fast(tmp_path):
    with pytest.raises(RuntimeError):
        create_app(make_settings(web_dist=tmp_path / "nope"))
