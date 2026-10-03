"""ndjson -> compact stroke arrays + train/val/test split.

Output: data/processed/sketches.pkl = {"train"|"val"|"test": (list[np.ndarray(N,3) float32], np.ndarray labels)}
Usage: python -m src.data.preprocess [--train 3200 --val 300 --test 300]
"""
import argparse
import json
import pickle

import numpy as np

from src.common import CLASSES, DATA_DIR, RAW_DIR


def parse(line: str):
    rec = json.loads(line)
    if not rec.get("recognized"):
        return None
    rows = []
    for xs, ys in rec["drawing"]:
        n = len(xs)
        if n == 0:
            continue
        ends = np.zeros(n, np.float32)
        ends[-1] = 1.0
        rows.append(np.stack([np.asarray(xs, np.float32), np.asarray(ys, np.float32), ends], axis=1))
    if not rows:
        return None
    pts = np.concatenate(rows)
    return pts if len(pts) >= 4 else None


def main(n_train: int, n_val: int, n_test: int) -> None:
    need = n_train + n_val + n_test
    out = {s: ([], []) for s in ("train", "val", "test")}
    for label, name in enumerate(CLASSES):
        path = RAW_DIR / f"{name.replace(' ', '_')}.ndjson"
        sketches = []
        with open(path, encoding="utf-8") as f:
            for line in f:
                p = parse(line)
                if p is not None:
                    sketches.append(p)
                if len(sketches) >= need:
                    break
        if len(sketches) < need:
            print(f"warning: {name} has only {len(sketches)} usable sketches (wanted {need})")
        bounds = [0, n_train, n_train + n_val, need]
        for split, (a, b) in zip(("train", "val", "test"), zip(bounds[:-1], bounds[1:])):
            chunk = sketches[a:b]
            out[split][0].extend(chunk)
            out[split][1].extend([label] * len(chunk))
        print(f"{name:12s} {len(sketches)}")
    out = {k: (v[0], np.asarray(v[1], np.int64)) for k, v in out.items()}
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    with open(DATA_DIR / "sketches.pkl", "wb") as f:
        pickle.dump(out, f, protocol=4)
    print({k: len(v[0]) for k, v in out.items()})


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--train", type=int, default=3200)
    ap.add_argument("--val", type=int, default=300)
    ap.add_argument("--test", type=int, default=300)
    a = ap.parse_args()
    main(a.train, a.val, a.test)
