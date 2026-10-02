"""Stream the first chunk of each QuickDraw 'simplified' ndjson (stroke-level data).

Uses HTTP Range requests so we never download the multi-GB full files.
Usage: python -m src.data.download [--mb 10]
"""
import argparse
import sys
import urllib.parse
import urllib.request

from src.common import CLASSES, RAW_DIR

URL = "https://storage.googleapis.com/quickdraw_dataset/full/simplified/{}.ndjson"


def fetch(name: str, mb: int) -> None:
    out = RAW_DIR / f"{name.replace(' ', '_')}.ndjson"
    if out.exists() and out.stat().st_size > 0:
        print(f"skip {name} (exists)")
        return
    url = URL.format(urllib.parse.quote(name))
    req = urllib.request.Request(url, headers={"Range": f"bytes=0-{mb * 1024 * 1024 - 1}"})
    with urllib.request.urlopen(req, timeout=120) as r:
        data = r.read()
    data = data[: data.rfind(b"\n") + 1]  # drop the truncated last line
    out.write_bytes(data)
    n = data.count(b"\n")
    print(f"{name}: {len(data) / 1e6:.1f} MB, {n} sketches", flush=True)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--mb", type=int, default=10)
    args = ap.parse_args()
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    for c in CLASSES:
        try:
            fetch(c, args.mb)
        except Exception as e:  # noqa: BLE001
            print(f"FAILED {c}: {e}", file=sys.stderr)
