"""Evaluate a model version (its sketch.onnx) on held-out sketches.

Mirrors apps/api/app/inference.py (the server's scorer) and the browser: cut the drawing to a fraction of its ink, simplify with RDP,
featurise, run. A test in the API suite asserts that this module and the server's Scorer return the same probabilities.
"""
import json
from pathlib import Path

import numpy as np
import onnxruntime as ort

from src.common import ROOT
from src.data import partial

MODELS = ROOT / "models"
FRACTIONS = (0.2, 0.3, 0.5)          # the early-recognition regime the project is about


def as_array(strokes) -> np.ndarray:
    """Strokes ([[x, y], ...] per stroke) -> (N, 3) float32 rows x, y, end-of-stroke flag: the training pipeline's format."""
    rows = []
    for s in strokes:
        for i, (x, y) in enumerate(s):
            rows.append((x, y, 1.0 if i == len(s) - 1 else 0.0))
    return np.asarray(rows, np.float32)


class OnnxModel:
    def __init__(self, version: str, models_dir: Path = MODELS):
        folder = models_dir / version
        self.version = version
        self.classes: list[str] = json.loads((folder / "meta.json").read_text(encoding="utf-8"))["classes"]
        self.session = ort.InferenceSession(str(folder / "sketch.onnx"), providers=["CPUExecutionProvider"])

    def probabilities(self, raw: np.ndarray, fraction: float) -> np.ndarray:
        part = partial.cut_prefix(raw, fraction)
        simplified = as_array([partial.rdp(s.astype(np.float64), 2.0) for s in partial.split_strokes(part)])
        seq, length = partial.to_seq(simplified)
        out = self.session.run(["probs"], {
            "img": partial.render(simplified)[None, None].astype(np.float32),
            "seq": seq[None].astype(np.float32),
            "length": np.array([length], dtype=np.int64),
        })
        return out[0][0]


def evaluate(model: OnnxModel, sketches: list[np.ndarray], labels: list[str], fractions=FRACTIONS, restrict_to: set[str] | None = None,
             only_labels: set[str] | None = None) -> dict:
    """Top-1 / Top-5 per fraction over the sketches whose label the model knows.

    Two independent switches. `only_labels` chooses WHICH sketches are scored (those whose label is in the set). `restrict_to` chooses what the
    model may ANSWER: only those classes, everything else masked out; that makes a 30-class model and a 100-class model comparable on the 30
    classes they share. When only `restrict_to` is given it also selects the sketches (the classic comparison). With neither, every sketch of a
    known class is scored and the model chooses among all its own classes. To ask how a big model does on a few classes while it still has to
    rule out all the others, pass only_labels and leave restrict_to unset.
    Returns {"n": count, "fractions": {"0.2": {"top1": .., "top5": ..}, ...}}.
    """
    known = {c: i for i, c in enumerate(model.classes)}
    allowed = np.array([c in restrict_to for c in model.classes]) if restrict_to is not None else np.ones(len(model.classes), bool)
    scope = only_labels if only_labels is not None else restrict_to
    keep = [k for k, lab in enumerate(labels) if lab in known and (scope is None or lab in scope)]
    out = {}
    for f in fractions:
        c1 = c5 = 0
        for k in keep:
            p = np.where(allowed, model.probabilities(sketches[k], f), -1.0)
            top5 = np.argsort(-p)[:5]
            c1 += int(top5[0] == known[labels[k]])
            c5 += int(known[labels[k]] in top5)
        n = max(1, len(keep))
        out[str(f)] = {"top1": c1 / n, "top5": c5 / n}
    return {"n": len(keep), "fractions": out}


def mean_top5(result: dict) -> float:
    vals = [v["top5"] for v in result["fractions"].values()]
    return sum(vals) / len(vals)
