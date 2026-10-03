"""Export a few REAL held-out test sketches (never trained on) for the web app's replay mode.

python -m src.export.samples [--per-class 3] [--version v1]
"""
import argparse
import json

import numpy as np

from src.common import CLASSES, ROOT
from src.data.dataset import load_splits
from src.data.partial import split_strokes


def main(per_class: int, version: str):
    sk, lb = load_splits()["test"]
    rng = np.random.default_rng(1)
    out = []
    for c, name in enumerate(CLASSES):
        idx = np.flatnonzero(lb == c)
        for i in rng.choice(idx, size=min(per_class, len(idx)), replace=False):
            strokes = [np.round(s).astype(int).tolist() for s in split_strokes(sk[i])]
            out.append({"label": name, "strokes": strokes})
    path = ROOT / "models" / version / "samples.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    json.dump(out, open(path, "w"), separators=(",", ":"))
    print(f"wrote {len(out)} sketches -> {path}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--per-class", type=int, default=3)
    ap.add_argument("--version", default="v1")
    a = ap.parse_args()
    main(a.per_class, a.version)
