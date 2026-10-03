"""Package the built web app for a machine with only a browser and Python 3 (e.g. a lab PC).

npm run build:web && python scripts/make_web_bundle.py      ->  dist/prescribble-web.zip
Unzip, run `bash run.sh` (Linux/macOS) or `run.bat` (Windows), and open http://localhost:8765. No backend: the app starts in
offline mode (the Studio works fully; accounts need the server).
"""
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
WEB = ROOT / "apps" / "web"
DIST = WEB / "dist"
OUT = ROOT / "dist" / "prescribble-web.zip"
TOP = "prescribble-web"

RUN_SH = """#!/usr/bin/env bash
# Starts the local server and opens the browser.
cd "$(dirname "$0")" || exit 1
PORT="${1:-8765}"
URL="http://localhost:${PORT}"
PY="$(command -v python3 || command -v python)"
if [ -z "$PY" ]; then echo "Python 3 not found. Install it with: sudo apt install python3"; exit 1; fi
( sleep 1; (xdg-open "$URL" || open "$URL" || echo "Open $URL in your browser") >/dev/null 2>&1 ) &
exec "$PY" serve.py "$PORT"
"""
RUN_BAT = "@echo off\r\ncd /d \"%~dp0\"\r\nstart \"\" http://localhost:8765\r\npython serve.py 8765\r\n"


def main():
    required = ["index.html", "ort/ort-wasm-simd-threaded.wasm", "ort/ort-wasm-simd-threaded.mjs", "models/v1/sketch.onnx", "models/v1/meta.json"]
    missing = [f for f in required if not (DIST / f).exists()]
    if missing:
        raise SystemExit(f"web build incomplete ({missing}). Run: npm run build:web")
    OUT.parent.mkdir(exist_ok=True)
    with zipfile.ZipFile(OUT, "w", zipfile.ZIP_DEFLATED) as z:
        for p in sorted(DIST.rglob("*")):
            if p.is_file():
                z.write(p, f"{TOP}/dist/{p.relative_to(DIST).as_posix()}")
        z.write(WEB / "serve.py", f"{TOP}/serve.py")
        sh = zipfile.ZipInfo(f"{TOP}/run.sh")
        sh.external_attr = 0o755 << 16
        sh.compress_type = zipfile.ZIP_DEFLATED
        z.writestr(sh, RUN_SH)                       # LF endings, executable
        z.writestr(f"{TOP}/run.bat", RUN_BAT)
    print(f"wrote {OUT} ({OUT.stat().st_size / 1e6:.1f} MB)")


if __name__ == "__main__":
    main()
