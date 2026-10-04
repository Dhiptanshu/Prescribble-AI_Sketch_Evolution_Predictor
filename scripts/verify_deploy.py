"""Check a running deployment end to end over HTTP (a container, a VM, a platform service): is it really serving the whole product?

python scripts/verify_deploy.py http://localhost:8200 [--restart-container presctest-app-1]
Creates one throwaway account on that server (and deletes it at the end). Exit code 0 only if every check passes.
Needs `pip install httpx websockets` on the machine running the check.
"""
import argparse
import asyncio
import json
import secrets
import subprocess
import sys

import httpx
import websockets

results: list[tuple[bool, str]] = []


def check(ok: bool, what: str, detail: str = "") -> bool:
    results.append((ok, what))
    print(("PASS " if ok else "FAIL ") + what + (f"  [{detail}]" if detail and not ok else ""), flush=True)
    return ok


async def room_socket(base: str, room_id: int, cookies: httpx.Cookies) -> dict:
    url = base.replace("http", "ws", 1) + f"/api/v1/rooms/{room_id}/live"
    cookie = "; ".join(f"{k}={v}" for k, v in cookies.items())
    async with websockets.connect(url, additional_headers={"Cookie": cookie}) as ws:
        return json.loads(await asyncio.wait_for(ws.recv(), 10))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("base")
    ap.add_argument("--restart-container", help="restart this Docker container and check the data survives (proves the volume works)")
    a = ap.parse_args()
    base = a.base.rstrip("/")
    c = httpx.Client(base_url=base, timeout=30)

    r = c.get("/healthz")
    check(r.status_code == 200, "health check answers", r.text)
    page = c.get("/")
    check(page.status_code == 200 and "<div id=\"root\">" in page.text, "the web app is served at /")
    check("content-security-policy" in page.headers and page.headers.get("x-content-type-options") == "nosniff" and page.headers.get("x-frame-options") == "DENY",
          "the page carries the content security policy and security headers", str(dict(page.headers)))
    check(c.get("/some/client/route").status_code == 200, "deep links fall back to the app (a refresh works)")

    registry = c.get("/models/registry.json").json()
    active = registry["active"]
    check(c.get("/models/registry.json").headers.get("cache-control") == "no-cache", "the registry is never cached")
    onnx = c.head(f"/models/{active}/sketch.onnx")
    check(onnx.status_code == 200 and "immutable" in onnx.headers.get("cache-control", ""), f"the live model ({active}) is served and cacheable", str(onnx.headers))
    check(c.get("/ort/ort-wasm-simd-threaded.wasm", headers={"Range": "bytes=0-3"}).headers.get("content-type", "").startswith("application/wasm"),
          "the WebAssembly runtime has the right content type")
    meta = c.get(f"/models/{active}/meta.json").json()
    info = c.get("/api/v1/model").json()
    check(info["version"] == active and info["classes"] == meta["classes"], f"the API and the web app agree on the live model ({active}, {len(meta['classes'])} classes)")
    check(c.get("/api/docs").status_code == 200, "the API reference page loads")

    email, password = f"verify.{secrets.token_hex(4)}@example.com", secrets.token_urlsafe(18)
    r = c.post("/api/v1/auth/register", json={"email": email, "password": password, "display_name": "Deploy Check"})
    check(r.status_code == 201, "an account can be created", r.text)
    strokes = [[[20, 200], [128, 40], [236, 200], [20, 200]]]
    drawing = {"strokes": strokes, "label": meta["classes"][0], "ai_guess": meta["classes"][0], "ai_confidence": 0.5, "model_version": active, "label_confirmed": True}
    r = c.post("/api/v1/drawings", json=drawing)
    check(r.status_code == 201, "a drawing can be saved", r.text)
    check(len(c.get("/api/v1/drawings").json()["items"]) == 1, "the saved drawing is listed")
    evil = c.post("/api/v1/drawings", json=drawing, headers={"Origin": "https://evil.example"})
    check(evil.status_code == 403 and evil.json()["error"]["code"] == "bad_origin", "a write from another site is refused", evil.text)

    key = c.post("/api/v1/keys", json={"name": "deploy check"}).json()
    r = httpx.post(base + "/api/v1/predict", json={"strokes": strokes, "top_k": 3}, headers={"Authorization": f"Bearer {key['key']}"}, timeout=30)
    check(r.status_code == 200 and len(r.json()["predictions"]) == 3 and r.json()["model"] == active, "the prediction API answers with the live model", r.text)
    check(httpx.post(base + "/api/v1/predict", json={"strokes": strokes}, headers={"Authorization": f"Bearer {key['key']}", "Origin": "https://x.example"}, timeout=30).status_code == 403,
          "an API key is refused when it comes from a browser")

    day = c.get("/api/v1/challenge/today").json()
    check(day["target"] in meta["classes"] and day["model_version"] == active, f"today's challenge word comes from the live model ({day['target']})")
    room = c.post("/api/v1/rooms", json={"name": "deploy check"}).json()
    state = asyncio.run(room_socket(base, room["id"], c.cookies))
    check(state["role"] == "teacher" and state["room"]["code"] == room["code"], "the live classroom WebSocket connects and pushes state")

    if a.restart_container:
        subprocess.run(["docker", "restart", a.restart_container], check=True, capture_output=True)
        for _ in range(60):
            try:
                if httpx.get(base + "/healthz", timeout=3).status_code == 200:
                    break
            except httpx.HTTPError:
                pass
            asyncio.run(asyncio.sleep(1))
        r = c.post("/api/v1/auth/login", json={"email": email, "password": password})
        check(r.status_code == 200 and len(c.get("/api/v1/drawings").json()["items"]) == 1, "after a restart the account and its drawing are still there (the volume works)", r.text)

    r = c.request("DELETE", "/api/v1/me", json={"password": password})
    check(r.status_code == 204, "the throwaway account is deleted again", r.text)
    failed = [w for ok, w in results if not ok]
    print(f"\n{len(results) - len(failed)} of {len(results)} checks passed")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
