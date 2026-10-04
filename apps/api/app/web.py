"""Serve the built web app (apps/web/dist) from the API for single-container deployments.

Real files are served as-is; any other non-API path falls back to index.html so client-side routes (/studio) survive a refresh.
Fingerprinted assets and versioned model files are cached for a year; everything else is revalidated.
"""
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, Response

from app.errors import ApiError
from app.middleware import CONTENT_SECURITY_POLICY

# Only fingerprinted (assets/) and versioned (models/vN/) files are immutable. Fixed-name files (ort/, index.html) are revalidated via ETag.
_IMMUTABLE = ("assets/", "models/")
_REVALIDATED = ("models/registry.json",)           # the one fixed-name file under models/: it changes when a version is promoted
# Never trust the host's mime registry (Windows maps .mjs to text/plain, and browsers refuse such module scripts).
_MEDIA_TYPES = {".js": "text/javascript", ".mjs": "text/javascript", ".wasm": "application/wasm", ".onnx": "application/octet-stream",
                ".json": "application/json", ".css": "text/css", ".html": "text/html; charset=utf-8", ".svg": "image/svg+xml"}
_API_PREFIXES = ("api/", "healthz")
# What the embeddable widget loads from other people's websites (script, model, WebAssembly runtime): public, read-only files.
_CROSS_ORIGIN = ("widget/", "models/", "ort/")
_CROSS_ORIGIN_HEADERS = {"Access-Control-Allow-Origin": "*", "Cross-Origin-Resource-Policy": "cross-origin"}


def install_web(app: FastAPI, dist: Path) -> None:
    dist = dist.resolve()
    index = dist / "index.html"
    if not index.is_file():
        raise RuntimeError(f"web dist not found: {index} (build the web app first)")

    @app.api_route("/{path:path}", methods=["GET", "HEAD"], include_in_schema=False)       # HEAD: proxies, CDNs and health tools ask for headers only
    def spa(path: str, request: Request) -> Response:
        if path.startswith(_API_PREFIXES):
            raise ApiError(404, "not_found", "Not found")
        target = (dist / path).resolve() if path else index
        if target.is_file() and dist in target.parents:            # no path traversal outside dist
            immutable = path.startswith(_IMMUTABLE) and path not in _REVALIDATED
            headers = {"Cache-Control": "public, max-age=31536000, immutable" if immutable else "no-cache"}
            if path.startswith(_CROSS_ORIGIN):
                headers.update(_CROSS_ORIGIN_HEADERS)
            if target.suffix.lower() == ".html":
                headers["Content-Security-Policy"] = CONTENT_SECURITY_POLICY
            return FileResponse(target, media_type=_MEDIA_TYPES.get(target.suffix.lower()), headers=headers)
        if "." in Path(path).name:                                   # a missing asset must be a real 404, not index.html
            raise ApiError(404, "not_found", "Not found")
        return FileResponse(index, headers={"Cache-Control": "no-cache", "Content-Security-Policy": CONTENT_SECURITY_POLICY})
