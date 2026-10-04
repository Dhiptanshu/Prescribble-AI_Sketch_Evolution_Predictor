"""The comparison behind a promotion: is the candidate at least as good as the live model on the classes both know?

Two yardsticks, each measured on drawings neither model trained on:
  quickdraw  held-out QuickDraw sketches (the heldout pickle written by the training kernel)
  user       held-out drawings of real people (the consented export), only when there are enough of them (min_user)
Metric: Top-5 accuracy averaged over 20%, 30% and 50% of the ink, with both models restricted to the shared classes (so a 100-class model is
not penalised for also knowing 70 more). The unmasked number of the candidate is reported too. Dropping a class the live model knows fails the gate.
"""
import pickle
from pathlib import Path

from src.flywheel import dataset
from src.flywheel.onnx_eval import FRACTIONS, OnnxModel, as_array, evaluate, mean_top5


def _quickdraw(path: Path, per_class: int) -> tuple[list, list[str]]:
    d = pickle.load(open(path, "rb"))
    names = d["classes"]
    seen: dict[int, int] = {}
    sketches, labels = [], []
    for s, y in zip(d["sketches"], d["labels"]):
        y = int(y)
        if seen.get(y, 0) < per_class:
            seen[y] = seen.get(y, 0) + 1
            sketches.append(s)
            labels.append(names[y])
    return sketches, labels


def _yardstick(active: OnnxModel, cand: OnnxModel, sketches, labels, shared: set[str], tolerance: float) -> dict:
    a = evaluate(active, sketches, labels, restrict_to=shared)
    c = evaluate(cand, sketches, labels, restrict_to=shared)
    free = evaluate(cand, sketches, labels, only_labels=shared, restrict_to=None)     # the SAME sketches, but the candidate may answer with any of its classes
    ma, mc = mean_top5(a), mean_top5(c)
    return {"n": a["n"], "active_top5": ma, "candidate_top5": mc, "delta": mc - ma, "candidate_unmasked_top5": mean_top5(free), "candidate_unmasked_n": free["n"],
            "ok": mc >= ma - tolerance, "by_fraction": {"active": a["fractions"], "candidate": c["fractions"], "candidate_unmasked": free["fractions"]}}


def compare(models_dir: Path, candidate: str, active: str, heldout: Path, user_eval: Path | None = None, tolerance: float = 0.01,
            min_user: int = 30, per_class: int = 30) -> dict:
    act, cand = OnnxModel(active, models_dir), OnnxModel(candidate, models_dir)
    shared = set(act.classes) & set(cand.classes)
    dropped = sorted(set(act.classes) - set(cand.classes))
    verdict: dict = {"shared_classes": len(shared), "dropped_classes": dropped, "fractions": list(FRACTIONS), "tolerance": tolerance}
    checks = [not dropped and bool(shared)]
    sketches, labels = _quickdraw(heldout, per_class)
    verdict["quickdraw"] = _yardstick(act, cand, sketches, labels, shared, tolerance)
    checks.append(verdict["quickdraw"]["ok"])
    if user_eval is not None:
        records = dataset.read_jsonl(user_eval)
        _, held = dataset.split(records)
        if len(held) >= min_user:
            verdict["user"] = _yardstick(act, cand, [as_array(r["strokes"]) for r in held], [r["label"] for r in held], shared, tolerance)
            checks.append(verdict["user"]["ok"])
        else:
            verdict["user"] = {"skipped": f"only {len(held)} held-out real drawings, need at least {min_user}"}
    return {"passed": all(checks), "verdict": verdict}
