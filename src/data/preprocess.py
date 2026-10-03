"""ndjson -> compact stroke arrays + train/val/test split.

Small class sets (v1, v2): data/processed[/<set>]/sketches.pkl = {"train"|"val"|"test": (list[np.ndarray(N,3) float32], labels)}
    python -m src.data.preprocess [--train 3200 --val 300 --test 300]
Large class sets (v3): a packed, memory-mappable folder (src/data/packed.py), built in parallel
    python -m src.data.preprocess --packed [--train 24000]

Split rule of the packed form, per class, over the class's recognised drawings in file order: test = drawings 6300..6599 and validation = 6000..6099
(the same test drawings as the 100-class model's, which neither v1 nor v2 ever trained on, so every model generation can be compared on them);
training = everything else, up to --train (drawings 0..5999, 6100..6299, then 6600 onwards).
"""
import argparse
import json
import multiprocessing as mp
import pickle

import numpy as np

from src.common import CLASSES, DATA_DIR, RAW_DIR
from src.data.packed import PackedSketches

TEST_SLICE, VAL_SLICE = (6300, 6600), (6000, 6100)
TRAIN_SLICES = ((0, 6000), (6100, 6300), (6600, None))


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


def read_usable(name: str, need: int) -> list[np.ndarray]:
    path = RAW_DIR / f"{name.replace(' ', '_')}.ndjson"
    sketches: list[np.ndarray] = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            p = parse(line)
            if p is not None:
                sketches.append(p)
            if len(sketches) >= need:
                break
    return sketches


# ------------------------------------------------------------------ pickle form (small class sets)

def main(n_train: int, n_val: int, n_test: int) -> None:
    need = n_train + n_val + n_test
    out = {s: ([], []) for s in ("train", "val", "test")}
    for label, name in enumerate(CLASSES):
        sketches = read_usable(name, need)
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


# ------------------------------------------------------------------ packed form (large class sets)

def packed_indices(n_usable: int, n_train: int) -> dict[str, list[int]]:
    """Which of a class's usable drawings (by position) go to each split."""
    clip = lambda lo, hi: list(range(lo, min(hi if hi is not None else n_usable, n_usable)))      # noqa: E731
    train = [i for lo, hi in TRAIN_SLICES for i in clip(lo, hi)][:n_train]
    return {"train": train, "val": clip(*VAL_SLICE), "test": clip(*TEST_SLICE)}


def _class_job(args):
    label, name, n_train = args
    need = max(n_train + 400, TEST_SLICE[1])             # always read far enough to reach the held-out drawings
    usable = read_usable(name, need)
    idx = packed_indices(len(usable), n_train)
    pieces = {}
    for split, ids in idx.items():
        arrays = [np.clip(np.rint(usable[i]), 0, 255).astype(np.uint8) for i in ids]
        lengths = np.fromiter((len(a) for a in arrays), np.int64, count=len(arrays))
        pieces[split] = (np.concatenate(arrays) if arrays else np.zeros((0, 3), np.uint8), lengths)
    return label, name, len(usable), pieces


def main_packed(n_train: int, processes: int, limit_classes: int | None = None) -> None:
    classes = CLASSES[:limit_classes]                                        # limit_classes is a testing aid: the first N classes only
    parts = {s: ([], [], []) for s in ("train", "val", "test")}            # points, lengths, labels
    short = []
    with mp.Pool(processes) as pool:
        for k, (label, name, n_usable, pieces) in enumerate(pool.imap(_class_job, [(i, c, n_train) for i, c in enumerate(classes)]), 1):
            if n_usable < max(n_train + 400, TEST_SLICE[1]):
                short.append((name, n_usable))
            for split, (pts, lengths) in pieces.items():
                parts[split][0].append(pts)
                parts[split][1].append(lengths)
                parts[split][2].append(np.full(len(lengths), label, np.int16))
            if k % 25 == 0 or k == len(classes):
                print(f"[{k}/{len(classes)}] {name}: {n_usable} usable drawings", flush=True)
    root = DATA_DIR / "packed"
    for split, (pts, lengths, labels) in parts.items():
        lengths, labels = np.concatenate(lengths), np.concatenate(labels)
        PackedSketches(np.concatenate(pts), np.concatenate([[0], np.cumsum(lengths)])).save(root, split, labels)
        print(f"{split}: {len(labels)} drawings, {sum(len(p) for p in pts) / 1e6:.1f} M points", flush=True)
    if short:
        print(f"{len(short)} classes had fewer than {max(n_train + 400, TEST_SLICE[1])} usable drawings in the downloaded part (they train on fewer); fewest:",
              sorted(short, key=lambda s: s[1])[:5])


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--train", type=int, default=3200)
    ap.add_argument("--val", type=int, default=300)
    ap.add_argument("--test", type=int, default=300)
    ap.add_argument("--packed", action="store_true")
    ap.add_argument("--processes", type=int, default=4)
    ap.add_argument("--limit-classes", type=int, help="packed form: only the first N classes (testing aid)")
    a = ap.parse_args()
    if a.packed:
        main_packed(a.train, a.processes, a.limit_classes)
    else:
        main(a.train, a.val, a.test)
