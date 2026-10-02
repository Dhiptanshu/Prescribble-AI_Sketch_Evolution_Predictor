"""Package the self-contained demo into dist/sketch-evolution-demo.zip (copy it to a USB stick).

python scripts/make_bundle.py
The zip needs nothing but a browser and Python 3 on the target machine.
"""
import shutil
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DEMO = ROOT / "demo"
OUT = ROOT / "dist" / "sketch-evolution-demo.zip"

REQUIRED = ["index.html", "serve.py", "models/sketch.onnx", "models/meta.json", "models/results.json", "models/samples.json",
            "vendor/ort/ort.wasm.min.js", "vendor/ort/ort-wasm-simd-threaded.wasm", "vendor/ort/ort-wasm-simd-threaded.mjs"]


def sync_models():
    """models/v1 is the single tracked copy of the model; the legacy demo gets it copied in (demo/models is git-ignored)."""
    src = ROOT / "models" / "v1"
    (DEMO / "models").mkdir(exist_ok=True)
    for f in src.iterdir():
        shutil.copy(f, DEMO / "models" / f.name)


def main():
    sync_models()
    missing = [f for f in REQUIRED if not (DEMO / f).exists()]
    if missing:
        raise SystemExit(f"missing demo files: {missing}")
    OUT.parent.mkdir(exist_ok=True)
    with zipfile.ZipFile(OUT, "w", zipfile.ZIP_DEFLATED) as z:
        for p in sorted(DEMO.rglob("*")):
            if p.is_file() and "__pycache__" not in p.parts and not p.name.startswith("_"):
                info = zipfile.ZipInfo.from_file(p, Path("sketch-evolution-demo") / p.relative_to(DEMO))
                if p.name == "run.sh":
                    info.external_attr = 0o755 << 16      # keep it executable on Linux
                info.compress_type = zipfile.ZIP_DEFLATED
                z.writestr(info, p.read_bytes())
    print(f"wrote {OUT} ({OUT.stat().st_size / 1e6:.1f} MB)")


if __name__ == "__main__":
    main()
