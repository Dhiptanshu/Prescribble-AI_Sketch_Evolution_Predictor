"""Pure ASGI middlewares (no body buffering, no per-request task): security headers, a request-body cap that also holds for chunked uploads, and a
cross-site check for writes that carry the session cookie.

Order in main.py (outermost first): security headers -> body cap -> cross-site check -> the app."""
import json
from urllib.parse import urlparse

from fastapi import HTTPException   # FastAPI's own class: it re-raises this one, and turns any other error raised while reading a body into a generic 400

UNSAFE_METHODS = {"POST", "PUT", "PATCH", "DELETE"}

# What the browser may load for the app's own pages. 'wasm-unsafe-eval' is what lets ONNX Runtime compile its WebAssembly; styles allow inline because the
# embeddable widget builds a <style> element in its shadow DOM; connect-src allows the live-room WebSocket. Applied to HTML only (see web.py): the
# API's own /api/docs page loads its viewer from a CDN and must not get it.
CONTENT_SECURITY_POLICY = ("default-src 'self'; script-src 'self' 'wasm-unsafe-eval'; style-src 'self' 'unsafe-inline'; img-src 'self' data: blob:; "
                           "media-src 'self' blob:; font-src 'self' data:; connect-src 'self' ws: wss:; worker-src 'self' blob:; object-src 'none'; "
                           "base-uri 'self'; form-action 'self'; frame-ancestors 'none'")


def _headers(scope) -> dict[str, str]:
    return {k.decode("latin-1").lower(): v.decode("latin-1") for k, v in scope.get("headers", [])}


class SecurityHeaders:
    """Headers every response should carry, whatever produced it. HSTS only when the deployment is HTTPS-only (secure cookies)."""

    def __init__(self, app, hsts: bool = False):
        self.app = app
        self.extra = [(b"x-content-type-options", b"nosniff"), (b"referrer-policy", b"strict-origin-when-cross-origin"), (b"x-frame-options", b"DENY"),
                      (b"permissions-policy", b"camera=(), microphone=(), geolocation=(), payment=()")]
        if hsts:
            self.extra.append((b"strict-transport-security", b"max-age=15552000; includeSubDomains"))

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)

        async def add(message):
            if message["type"] == "http.response.start":
                present = {k.lower() for k, _ in message["headers"]}
                message = {**message, "headers": [*message["headers"], *[(k, v) for k, v in self.extra if k not in present]]}
            await send(message)

        await self.app(scope, receive, add)


class BodyLimit:
    """Refuses a request body above `max_bytes`: by Content-Length up front, and by counting bytes as they arrive (a chunked upload has no length)."""

    def __init__(self, app, max_bytes: int):
        self.app, self.max = app, max_bytes

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        length = _headers(scope).get("content-length", "")
        if length.isdigit() and int(length) > self.max:
            return await _json(send, 413, "payload_too_large", "The request body is too large.")
        seen = 0

        async def counted():
            nonlocal seen
            message = await receive()
            if message["type"] == "http.request":
                seen += len(message.get("body", b""))
                if seen > self.max:
                    raise HTTPException(413, "The request body is too large.")
            return message

        await self.app(scope, counted, send)


class OriginGuard:
    """Defence in depth against cross-site request forgery: a write that arrives with the session cookie AND a browser Origin header must come from this
    site (same host, or an origin listed in PRESCRIBBLE_CORS_ORIGINS / PRESCRIBBLE_TRUSTED_ORIGINS). SameSite=Lax cookies already keep other sites from
    attaching the cookie; this refuses it even if a browser were to. Requests without the cookie (visitors, students with a room token, API keys) are
    not subject to it, because there is no ambient credential to abuse."""

    def __init__(self, app, cookie_name: str, trusted: list[str]):
        self.app, self.cookie, self.trusted = app, cookie_name, set(trusted)

    async def __call__(self, scope, receive, send):
        if scope["type"] == "http" and scope["method"] in UNSAFE_METHODS:
            h = _headers(scope)
            origin = h.get("origin")
            if origin and f"{self.cookie}=" in h.get("cookie", "") and not self._allowed(origin, h):
                return await _json(send, 403, "bad_origin", "This request came from another site and was refused.")
        await self.app(scope, receive, send)

    def _allowed(self, origin: str, h: dict[str, str]) -> bool:
        host = urlparse(origin).netloc
        return origin in self.trusted or host in {h.get("host", ""), h.get("x-forwarded-host", "")}


async def _json(send, status: int, code: str, message: str) -> None:
    body = json.dumps({"error": {"code": code, "message": message}}).encode()
    await send({"type": "http.response.start", "status": status, "headers": [(b"content-type", b"application/json"), (b"content-length", str(len(body)).encode())]})
    await send({"type": "http.response.body", "body": body})
