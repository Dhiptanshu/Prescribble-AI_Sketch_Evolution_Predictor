"""Stream the first chunk of each QuickDraw 'simplified' ndjson (stroke-level data) for the current class set.

Uses HTTP Range requests so we never download the multi-GB full files: the whole dataset is 24 GB (about 50 million drawings), far more than a
training session can use, so we take the first `--mb` megabytes of each class (about 650 bytes per drawing).
Usage: python -m src.data.download [--mb 10] [--threads 8]      (class set from PRESCRIBBLE_CLASS_SET)
"""
import argparse
import sys
import time
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor

from src.common import CLASSES, RAW_DIR

URL = "https://storage.googleapis.com/quickdraw_dataset/full/simplified/{}.ndjson"
RETRIES = 4


def fetch(name: str, mb: int) -> str:
    out = RAW_DIR / f"{name.replace(' ', '_')}.ndjson"
    wanted = mb * 1024 * 1024
    if out.exists() and out.stat().st_size >= wanted * 0.98:       # a file from a smaller request is fetched again
        return f"skip {name} (exists)"
    url = URL.format(urllib.parse.quote(name))
    req = urllib.request.Request(url, headers={"Range": f"bytes=0-{wanted - 1}"})
    for attempt in range(1, RETRIES + 1):
        try:
            with urllib.request.urlopen(req, timeout=180) as r:
                data = r.read()
            break
        except Exception:  # noqa: BLE001  (network hiccups are retried, the last one is raised)
            if attempt == RETRIES:
                raise
            time.sleep(2 * attempt)
    data = data[: data.rfind(b"\n") + 1]  # drop the truncated last line
    out.write_bytes(data)
    sketches = data.count(b"\n")
    return f"{name}: {len(data) / 1e6:.1f} MB, {sketches} sketches"


def main(mb: int, threads: int) -> int:
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    failed = []
    with ThreadPoolExecutor(threads) as pool:
        futures = {pool.submit(fetch, c, mb): c for c in CLASSES}
        for done, (fut, name) in enumerate(futures.items(), 1):
            try:
                print(f"[{done}/{len(CLASSES)}] {fut.result()}", flush=True)
            except Exception as e:  # noqa: BLE001
                failed.append(name)
                print(f"FAILED {name}: {e}", file=sys.stderr, flush=True)
    return 1 if failed else 0


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--mb", type=int, default=10)
    ap.add_argument("--threads", type=int, default=8)
    args = ap.parse_args()
    sys.exit(main(args.mb, args.threads))
