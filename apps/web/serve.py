"""Zero-dependency static server for the built web app, with single-page-app fallback.

python3 apps/web/serve.py [port]    ->  http://localhost:8765     (serves apps/web/dist)
Needs only Python 3. Unknown paths fall back to index.html so clean URLs like /studio work after a refresh.
When no backend is running, the app starts in offline mode: the Studio works, accounts do not.
"""
import http.server
import socketserver
import sys
from pathlib import Path

PORT = int(sys.argv[1]) if len(sys.argv) > 1 else 8765
ROOT = Path(__file__).resolve().parent / "dist"


class Handler(http.server.SimpleHTTPRequestHandler):
    extensions_map = {**http.server.SimpleHTTPRequestHandler.extensions_map,
                      ".wasm": "application/wasm", ".mjs": "text/javascript", ".js": "text/javascript",
                      ".onnx": "application/octet-stream", ".json": "application/json"}

    def __init__(self, *a, **k):
        super().__init__(*a, directory=str(ROOT), **k)

    def send_head(self):
        path = Path(self.translate_path(self.path))
        if not path.exists() and not self.path.startswith(("/api", "/healthz")) and "." not in Path(self.path).name:
            self.path = "/index.html"            # SPA route
        elif not path.exists() and self.path.startswith(("/api", "/healthz")):
            self.send_error(404, "API not available in static mode")
            return None
        return super().send_head()

    def end_headers(self):
        self.send_header("Cache-Control", "no-cache")
        super().end_headers()

    def log_message(self, *args):
        pass


if __name__ == "__main__":
    if not ROOT.exists():
        raise SystemExit("apps/web/dist not found. Build first: npm run build:web")
    socketserver.TCPServer.allow_reuse_address = True
    with socketserver.ThreadingTCPServer(("0.0.0.0", PORT), Handler) as srv:
        print(f"Prescribble running at http://localhost:{PORT}  (Ctrl+C to stop)")
        srv.serve_forever()
