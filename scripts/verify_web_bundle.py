"""Self-check for dist/prescribble-web.zip: unzip it somewhere fresh, run ITS server, probe everything the page needs.

python scripts/verify_web_bundle.py [path/to/prescribble-web.zip]
Prints "bundle OK" (exit 0) or the list of problems (exit 1). Standard library only.
"""
import ast
import json
import re
import socket
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DEFAULT = ROOT / "dist" / "prescribble-web.zip"
TOP = "prescribble-web"


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def get(url: str):
    try:
        with urllib.request.urlopen(url, timeout=15) as r:
            return r.status, r.headers.get("Content-Type", ""), r.read()
    except urllib.error.HTTPError as e:
        return e.code, e.headers.get("Content-Type", ""), e.read()


def check_archive(z: zipfile.ZipFile, problems: list) -> None:
    names = z.namelist()
    for n in names:
        if n.startswith("/") or ".." in n.split("/") or "\\" in n:
            problems.append(f"unsafe path in zip: {n}")
    for need in ("serve.py", "run.sh", "run.bat", "dist/index.html"):
        if f"{TOP}/{need}" not in names:
            problems.append(f"missing {need}")
    if f"{TOP}/run.sh" in names:
        info = z.getinfo(f"{TOP}/run.sh")
        if b"\r" in z.read(info):
            problems.append("run.sh has Windows line endings (would fail on Linux: '\\r: command not found')")
        if not (info.external_attr >> 16) & 0o111:
            problems.append("run.sh is not marked executable")
    if f"{TOP}/serve.py" in names:
        try:   # the lab may run Ubuntu 20.04 (Python 3.8): the server must at least parse under 3.8 grammar
            ast.parse(z.read(f"{TOP}/serve.py").decode(), feature_version=(3, 8))
        except SyntaxError as e:
            problems.append(f"serve.py is not valid Python 3.8: {e}")


def probe(base: str, root: Path, problems: list) -> None:
    def expect(path, status=200, ctype=None, min_size=0):
        code, ct, body = get(base + path)
        if code != status:
            problems.append(f"{path}: HTTP {code}, expected {status}")
        elif ctype and not ct.lower().startswith(ctype):
            problems.append(f"{path}: content-type {ct!r}, expected {ctype!r}")
        elif len(body) < min_size:
            problems.append(f"{path}: only {len(body)} bytes")
        return body

    html = expect("/", ctype="text/html", min_size=200).decode("utf-8", "replace")
    expect("/studio", ctype="text/html", min_size=200)                          # SPA fallback
    expect("/some/deep/route", ctype="text/html", min_size=200)
    for ref in re.findall(r'(?:src|href)="(/assets/[^"]+)"', html):
        expect(ref, ctype="text/javascript" if ref.endswith(".js") else "text/css", min_size=100)
    if not re.search(r'/assets/[^"]+\.js', html):
        problems.append("index.html references no JavaScript bundle")

    expect("/widget/prescribble-widget.js", ctype="text/javascript", min_size=10_000)           # the embeddable widget ships with the app
    expect("/ort/ort-wasm-simd-threaded.mjs", ctype="text/javascript", min_size=1000)   # module scripts must not be text/plain
    wasm = expect("/ort/ort-wasm-simd-threaded.wasm", ctype="application/wasm", min_size=1_000_000)
    if wasm[:4] != b"\x00asm":
        problems.append("ort wasm file does not start with the WebAssembly magic bytes")
    expect("/models/v1/sketch.onnx", min_size=1_000_000)
    for name in ("meta.json", "results.json", "samples.json"):
        body = expect(f"/models/v1/{name}", ctype="application/json", min_size=10)
        try:
            data = json.loads(body)
        except ValueError:
            problems.append(f"/models/v1/{name} is not valid JSON")
            continue
        if name == "meta.json" and not (data.get("classes") and data.get("test_results")):
            problems.append("meta.json lacks classes / test_results")
        if name == "samples.json" and not (isinstance(data, list) and data and data[0].get("strokes")):
            problems.append("samples.json has no sketches")
    code, _, _ = get(base + "/api/v1/auth/session")                              # no backend: the app must detect offline mode
    if code != 404:
        problems.append(f"/api/v1/auth/session returned {code}; a static bundle must answer 404 so the app starts in offline mode")


def main() -> int:
    zip_path = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT
    if not zip_path.exists():
        print(f"{zip_path} not found. Run: npm run build:web && python scripts/make_web_bundle.py")
        return 1
    problems: list = []
    with tempfile.TemporaryDirectory() as tmp:
        with zipfile.ZipFile(zip_path) as z:
            check_archive(z, problems)
            z.extractall(tmp)
        root = Path(tmp) / TOP
        port = free_port()
        proc = subprocess.Popen([sys.executable, "serve.py", str(port)], cwd=root, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
        try:
            base = f"http://127.0.0.1:{port}"
            for _ in range(60):
                if proc.poll() is not None:
                    problems.append("serve.py exited immediately: " + proc.stderr.read().decode(errors="replace")[-400:])
                    break
                try:
                    get(base + "/")
                    break
                except OSError:
                    time.sleep(0.25)
            else:
                problems.append("server did not start within 15 s")
            if not problems or proc.poll() is None:
                probe(base, root, problems)
        finally:
            proc.terminate()
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()
    if problems:
        print("bundle has problems:\n  - " + "\n  - ".join(problems))
        return 1
    print(f"bundle OK ({zip_path.stat().st_size / 1e6:.1f} MB): served from a clean folder, all files and content types correct")
    return 0


if __name__ == "__main__":
    sys.exit(main())
