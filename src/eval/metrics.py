"""Evaluation metrics on probability vectors. Pure NumPy, so every function is unit-tested on hand-worked cases (tests/test_eval_metrics.py).

Shapes: probs (N, C) for one completion fraction, y (N,) true class indices.
"""
import numpy as np


def wilson(k: int, n: int, z: float = 1.96) -> tuple[float, float]:
    """95% Wilson score interval for a proportion k/n. It reflects the size of the test sample only, not the variation between training runs."""
    if n == 0:
        return (float("nan"), float("nan"))
    p = k / n
    d = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / d
    half = z * np.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return (float(max(0.0, centre - half)), float(min(1.0, centre + half)))


def ranked(probs: np.ndarray, allowed: np.ndarray | None = None) -> np.ndarray:
    """Class indices from most to least likely. `allowed` (bool, C) rules the other classes out (they can never be answered)."""
    p = probs if allowed is None else np.where(allowed[None, :], probs, -1.0)
    return np.argsort(-p, axis=1, kind="stable")


def topk_hits(order: np.ndarray, y: np.ndarray, k: int) -> np.ndarray:
    return (order[:, :k] == y[:, None]).any(axis=1)


def confusion(pred: np.ndarray, y: np.ndarray, n_classes: int) -> np.ndarray:
    """Rows = true class, columns = predicted class."""
    m = np.zeros((n_classes, n_classes), np.int64)
    np.add.at(m, (y, pred), 1)
    return m


def macro_prf(conf: np.ndarray) -> dict:
    """Macro-averaged precision, recall and F1 over the classes that occur in the test set. A class never predicted has precision 0."""
    tp = np.diag(conf).astype(float)
    support = conf.sum(1).astype(float)
    predicted = conf.sum(0).astype(float)
    present = support > 0
    precision = np.divide(tp, predicted, out=np.zeros_like(tp), where=predicted > 0)
    recall = np.divide(tp, support, out=np.zeros_like(tp), where=support > 0)
    denom = precision + recall
    f1 = np.divide(2 * precision * recall, denom, out=np.zeros_like(tp), where=denom > 0)
    return {"precision": float(precision[present].mean()), "recall": float(recall[present].mean()), "f1": float(f1[present].mean()),
            "per_class_recall": np.where(present, recall, np.nan)}


def calibration(probs: np.ndarray, y: np.ndarray, bins: int = 15) -> dict:
    """Confidence calibration of the top-1 answer: expected calibration error, mean confidence, accuracy, and the per-bin curve."""
    conf = probs.max(1)
    correct = probs.argmax(1) == y
    edges = np.linspace(0, 1, bins + 1)
    which = np.clip(np.digitize(conf, edges[1:-1]), 0, bins - 1)
    curve, ece = [], 0.0
    for b in range(bins):
        m = which == b
        if m.any():
            gap = abs(conf[m].mean() - correct[m].mean())
            ece += m.mean() * gap
            curve.append({"confidence": float(conf[m].mean()), "accuracy": float(correct[m].mean()), "count": int(m.sum())})
    return {"ece": float(ece), "mean_confidence": float(conf.mean()), "accuracy": float(correct.mean()), "curve": curve}


def nll(probs: np.ndarray, y: np.ndarray) -> float:
    """Mean negative log-likelihood of the true class (lower is better)."""
    return float(-np.log(np.clip(probs[np.arange(len(y)), y], 1e-12, 1)).mean())


def brier(probs: np.ndarray, y: np.ndarray) -> float:
    """Multi-class Brier score: mean squared distance between the probability vector and the one-hot truth (lower is better)."""
    onehot = np.zeros_like(probs)
    onehot[np.arange(len(y)), y] = 1.0
    return float(((probs - onehot) ** 2).sum(1).mean())


def first_hit(correct: np.ndarray, fracs: np.ndarray, stays: bool = False) -> np.ndarray:
    """For each sketch the smallest completion fraction at which the top-1 answer is right (nan if never). correct: (N, F) bool.
    stays=True: the smallest fraction from which it is right at every later fraction too."""
    n, f = correct.shape
    out = np.full(n, np.nan)
    for i in range(n):
        if stays:
            for j in range(f):
                if correct[i, j:].all():
                    out[i] = fracs[j]
                    break
        else:
            hit = np.flatnonzero(correct[i])
            if len(hit):
                out[i] = fracs[hit[0]]
    return out


def top_confusions(conf: np.ndarray, classes: list[str], n: int = 10) -> list[tuple[str, str, int]]:
    """The n most frequent wrong (true, predicted) pairs."""
    off = conf.copy()
    np.fill_diagonal(off, 0)
    flat = np.argsort(-off, axis=None)[:n]
    return [(classes[i // conf.shape[1]], classes[i % conf.shape[1]], int(off[i // conf.shape[1], i % conf.shape[1]])) for i in flat if off.flat[i] > 0]
