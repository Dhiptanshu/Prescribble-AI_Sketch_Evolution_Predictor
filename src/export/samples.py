"""Export a few REAL held-out test sketches (never trained on) for the demo's replay mode.

python -m src.export.samples [--per-class 3]
"""
import argparse
import json

import numpy as np

from src.common import CLASSES, ROOT
from src.data.dataset import load_splits
from src.data.partial import split_strokes


def main(per_class: int):
    sk, lb = load_splits()["test"]
    rng = np.random.default_rng(1)
    out = []
    for c, name in enumerate(CLASSES):
        idx = np.flatnonzero(lb == c)
        for i in rng.choice(idx, size=min(per_class, len(idx)), replace=False):
            strokes = [np.round(s).astype(int).tolist() for s in split_strokes(sk[i])]
            out.append({"label": name, "strokes": strokes})
    path = ROOT / "demo" / "models" / "samples.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    json.dump(out, open(path, "w"), separators=(",", ":"))
    print(f"wrote {len(out)} sketches -> {path}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--per-class", type=int, default=3)
    main(ap.parse_args().per_class)
