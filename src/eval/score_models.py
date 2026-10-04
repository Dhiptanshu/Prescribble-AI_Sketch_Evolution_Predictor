"""Run the shipped ONNX models (v1, v2, v3) on the same held-out sketches and keep every probability vector.

    python -m src.eval.score_models [--per-class 25] [--workers 6]

The sketches are the first `--per-class` of the 50 held-out QuickDraw drawings per class in data/processed/v3/heldout.pkl. They come from a slice of
each class that v1, v2 and v3 never trained on (see src/data/preprocess.py), so all three are scored on the same unseen sketches. Each model is scored on
the sketches of its own classes, at every fraction in FRACS, through the same code path as the server (src/flywheel/onnx_eval.py).
Writes runs/eval/<version>.npz: probs (sketches, fractions, classes), y (index into the model's classes), sel (row in heldout.pkl), fracs, classes.
The metrics and figures are computed from these files by src/eval/model_report.py.
"""
import argparse
import pickle
import time
from concurrent.futures import ProcessPoolExecutor

import numpy as np
import onnxruntime as ort

from src.common import ROOT
from src.flywheel.onnx_eval import OnnxModel

FRACS = (0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.75, 0.9, 1.0)
VERSIONS = ("v1", "v2", "v3")
HELDOUT = ROOT / "data" / "processed" / "v3" / "heldout.pkl"
OUT = ROOT / "runs" / "eval"
CHUNK = 100

_state: dict = {}


def _init() -> None:
    with open(HELDOUT, "rb") as f:
        _state["held"] = pickle.load(f)
    _state["models"] = {}


def _model(version: str) -> OnnxModel:
    m = _state["models"].get(version)
    if m is None:
        m = OnnxModel(version)
        opts = ort.SessionOptions()
        opts.intra_op_num_threads, opts.inter_op_num_threads = 1, 1          # the workers already run in parallel
        m.session = ort.InferenceSession(str(ROOT / "models" / version / "sketch.onnx"), opts, providers=["CPUExecutionProvider"])
        _state["models"][version] = m
    return m


def _work(task: tuple[str, list[int]]):
    version, ids = task
    m, held = _model(version), _state["held"]
    out = np.zeros((len(ids), len(FRACS), len(m.classes)), np.float32)
    for r, i in enumerate(ids):
        for j, f in enumerate(FRACS):
            out[r, j] = m.probabilities(held["sketches"][i], f)
    return version, ids, out


def select(version: str, held: dict, per_class: int) -> tuple[list[int], np.ndarray, list[str]]:
    """Rows of the held-out file that belong to the model's classes (first `per_class` of each), their labels as indices into the model's classes."""
    classes = OnnxModel(version).classes
    position = {c: i for i, c in enumerate(classes)}
    names, labels = held["classes"], held["labels"]
    taken: dict[str, int] = {}
    rows, y = [], []
    for i, lab in enumerate(labels.tolist()):
        name = names[lab]
        if name in position and taken.get(name, 0) < per_class:
            taken[name] = taken.get(name, 0) + 1
            rows.append(i)
            y.append(position[name])
    return rows, np.asarray(y, np.int64), classes


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--per-class", type=int, default=25)
    ap.add_argument("--workers", type=int, default=6)
    ap.add_argument("--versions", nargs="+", default=list(VERSIONS))
    a = ap.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    _init()
    held = _state["held"]
    plans = {v: select(v, held, a.per_class) for v in a.versions}
    tasks = [(v, rows[k:k + CHUNK]) for v, (rows, _, _) in plans.items() for k in range(0, len(rows), CHUNK)]
    total = sum(len(r) for r, _, _ in plans.values())
    print(f"{total} sketches x {len(FRACS)} fractions across {len(a.versions)} models, {a.workers} workers", flush=True)
    results: dict[str, dict[int, np.ndarray]] = {v: {} for v in a.versions}
    t0, done = time.time(), 0
    with ProcessPoolExecutor(a.workers, initializer=_init) as pool:
        for version, ids, probs in pool.map(_work, tasks):
            results[version].update({i: probs[r] for r, i in enumerate(ids)})
            done += len(ids)
            print(f"  {done}/{total} sketches, {time.time() - t0:.0f} s", flush=True)
    for v, (rows, y, classes) in plans.items():
        probs = np.stack([results[v][i] for i in rows])
        np.savez_compressed(OUT / f"{v}.npz", probs=probs, y=y, sel=np.asarray(rows), fracs=np.asarray(FRACS), classes=np.asarray(classes))
        print(f"{v}: {len(rows)} sketches, {len(classes)} classes -> {OUT / (v + '.npz')}", flush=True)


if __name__ == "__main__":
    main()
