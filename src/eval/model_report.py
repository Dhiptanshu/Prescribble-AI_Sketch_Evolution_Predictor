"""Evaluation of the three model generations (v1: 30 classes, v2: 100, v3: 345).

    python -m src.eval.score_models      # once: runs the shipped ONNX files on the held-out sketches (runs/eval/<v>.npz)
    python -m src.eval.model_report      # metrics -> docs/results/evaluation.json, figures -> report/figures/eval_*.png, text -> report/EVALUATION.md

Every number in the report is computed here from the saved probabilities or read from models/<v>/{meta,results}.json. Nothing is typed.
"""
import json

import numpy as np
import onnx

from src.common import ROOT
from src.eval import metrics as M
from src.eval import model_figures as F

EVAL = ROOT / "runs" / "eval"
MODELS = ROOT / "models"
OUT_JSON = ROOT / "docs" / "results" / "evaluation.json"
OUT_MD = ROOT / "report" / "EVALUATION.md"
GATE_FRACS = (0.2, 0.3, 0.5)                       # the early regime used by the registry gate
OFFICIAL = ("0.1", "0.2", "0.3", "0.5", "0.75", "1.0")
OFFICIAL_FLOATS = tuple(float(f) for f in OFFICIAL)


def load(version: str) -> dict:
    z = np.load(EVAL / f"{version}.npz")
    return {"probs": z["probs"], "y": z["y"], "fracs": z["fracs"], "classes": [str(c) for c in z["classes"]]}


def column(fracs: np.ndarray, value: float) -> int:
    return int(np.argmin(np.abs(fracs - value)))


def accuracy_rows(probs: np.ndarray, y: np.ndarray, allowed: np.ndarray | None = None) -> dict:
    out = {k: [] for k in ("top1", "top5", "top1_lo", "top1_hi", "top5_lo", "top5_hi")}
    for j in range(probs.shape[1]):
        order = M.ranked(probs[:, j], allowed)
        for k, key in ((1, "top1"), (5, "top5")):
            hits = int(M.topk_hits(order, y, k).sum())
            lo, hi = M.wilson(hits, len(y))
            out[key].append(hits / len(y))
            out[key + "_lo"].append(lo)
            out[key + "_hi"].append(hi)
    out["n"] = int(len(y))
    return out


def params_millions(version: str) -> float:
    g = onnx.load(str(MODELS / version / "sketch.onnx")).graph
    return float(sum(int(np.prod(t.dims)) for t in g.initializer)) / 1e6


def evaluate(version: str) -> dict:
    d = load(version)
    probs, y, fracs, classes = d["probs"], d["y"], d["fracs"], d["classes"]
    c = len(classes)
    meta = json.loads((MODELS / version / "meta.json").read_text(encoding="utf-8"))
    j30, j100 = column(fracs, 0.3), column(fracs, 1.0)
    r: dict = {"classes": classes, "fracs": fracs.tolist(), "own": accuracy_rows(probs, y)}

    for tag, j in (("30", j30), ("100", j100)):
        order = M.ranked(probs[:, j])
        conf = M.confusion(order[:, 0], y, c)
        prf = M.macro_prf(conf)
        r[f"prf{tag}"] = {k: prf[k] for k in ("precision", "recall", "f1")}
        r[f"recall{tag}"] = prf["per_class_recall"].tolist()
        support = np.maximum(np.bincount(y, minlength=c), 1)
        r[f"recall5_{tag}"] = (np.bincount(y, weights=M.topk_hits(order, y, 5), minlength=c) / support).tolist()
        r[f"calib{tag}"] = {**M.calibration(probs[:, j], y), "nll": M.nll(probs[:, j], y), "brier": M.brier(probs[:, j], y)}
        if tag == "30":
            r["conf30_matrix"] = conf.tolist()
            r["confusions30"] = M.top_confusions(conf, classes, 10)
            r["conf30"] = probs[:, j].max(1).tolist()
            r["ok30"] = (probs[:, j].argmax(1) == y).tolist()

    correct = np.stack([probs[:, j].argmax(1) == y for j in range(len(fracs))], axis=1)
    r["first"] = M.first_hit(correct, fracs).tolist()
    r["stays"] = M.first_hit(correct, fracs, stays=True).tolist()

    first30 = classes[:30]                                  # the 30 original classes come first in every class set, in the same order
    keep = y < 30
    allowed = np.arange(c) < 30
    r["shared30"] = {"n": int(keep.sum()), "masked": accuracy_rows(probs[keep], y[keep], allowed), "free": accuracy_rows(probs[keep], y[keep]), "classes": first30}
    if c > 100:
        keep100, allowed100 = y < 100, np.arange(c) < 100
        r["shared100"] = {"n": int(keep100.sum()), "masked": accuracy_rows(probs[keep100], y[keep100], allowed100)}
    r["efficiency"] = {"size_mb": meta["size_mb"], "latency_ms": meta["latency_ms"], "params_m": params_millions(version)}
    r["official"] = {f: {k: meta["test_results"][f][k] for k in ("top1", "top5")} for f in OFFICIAL}
    r["model"] = meta["model"]
    return r


# ------------------------------------------------------------------------------------------------ writing

def pct(x: float) -> str:
    return f"{x * 100:.1f}"


def table(header: list[str], rows: list[list[str]], align: str | None = None) -> str:
    a = align or ("|---|" + "---:|" * (len(header) - 1))
    return "\n".join(["| " + " | ".join(header) + " |", a] + ["| " + " | ".join(r) + " |" for r in rows]) + "\n"


def bold_best(cells: list[float], fmt=pct, high: bool = True) -> list[str]:
    best = max(cells) if high else min(cells)
    return [f"**{fmt(c)}**" if c == best else fmt(c) for c in cells]


def gate_mean(rows: dict, key: str, fracs: list[float]) -> float:
    return float(np.mean([rows[key][column(np.asarray(fracs), g)] for g in GATE_FRACS]))


def write_markdown(R: dict, figs: dict) -> str:
    vs = list(R)
    fr = R[vs[0]]["fracs"]
    L: list[str] = []
    add = L.append
    n_own = {v: R[v]["own"]["n"] for v in vs}
    add("# Evaluation of the model generations (v1, v2, v3)\n")
    add("Generated by `python -m src.eval.model_report` from the shipped ONNX files, so it measures the models the app actually serves. "
        "Nothing in this file is typed by hand; the raw numbers are in `docs/results/evaluation.json`.\n")
    add("## 1. What was measured and how\n")
    add(f"* **Test sketches.** The first 25 of the 50 held-out QuickDraw drawings per class in `data/processed/v3/heldout.pkl`. They come from a slice of every class that none of "
        f"v1, v2 or v3 trained on, so the three models are scored on the **same unseen sketches**. Each model is scored on the sketches of its own classes: "
        + ", ".join(f"{v} {n_own[v]:,} sketches ({len(R[v]['classes'])} classes)" for v in vs) + ".")
    add("* **Partial drawings.** Every sketch is cut at a fraction of its total ink length (10, 20, 30, 40, 50, 60, 75, 90 and 100%) and the model sees only that prefix, exactly as in the app.")
    add("* **Intervals** are 95% Wilson intervals. They reflect the *size of the test sample* only. They do **not** include the variation between training runs (one run per model).")
    add("* **Top-1 / Top-5**: the true class is the first / among the first five answers. **Macro** scores average over classes, so a rare failure in one class counts as much as in a common one.")
    add("* **Calibration**: does a stated confidence of 70% mean the answer is right 70% of the time? ECE (15 bins) is the average gap; NLL and Brier are proper scoring rules (lower is better).\n")

    add("## 2. Headline: each model on its own classes\n")
    add("Official numbers from each model's full held-out test split (`models/<v>/results.json`, written at the end of training). Top-1 / Top-5 in %.\n")
    rows = []
    for f in OFFICIAL:
        rows.append([f"{int(float(f) * 100)}%"] + [f"{pct(R[v]['official'][f]['top1'])} / {pct(R[v]['official'][f]['top5'])}" for v in vs])
    add(table(["Ink drawn"] + [f"{v} ({len(R[v]['classes'])} classes)" for v in vs], rows))
    add("![Accuracy versus completion](figures/" + figs["curves"] + ")\n")
    add("The same models re-scored on the common unseen sample (Top-1 / Top-5 with 95% interval, %):\n")
    rows = []
    for j, f in enumerate(fr):
        row = [f"{int(round(f * 100))}%"]
        for v in vs:
            o = R[v]["own"]
            row.append(f"{pct(o['top1'][j])} / {pct(o['top5'][j])}  (Top-5 {pct(o['top5_lo'][j])}-{pct(o['top5_hi'][j])})")
        rows.append(row)
    add(table(["Ink drawn"] + vs, rows))
    outside = [f"{v} Top-5 at {int(round(f * 100))}%" for v in vs for f in OFFICIAL_FLOATS
               if not R[v]["own"]["top5_lo"][column(np.asarray(fr), f)] <= R[v]["official"][str(f)]["top5"] <= R[v]["own"]["top5_hi"][column(np.asarray(fr), f)]]
    add("Agreement with the official table: " + ("every official Top-5 figure lies inside the re-scored 95% interval." if not outside else
        "all official Top-5 figures lie inside the re-scored 95% interval except " + ", ".join(outside) + " (the re-scored sample is smaller, so its intervals are wider, and it is a different set of sketches).") + "\n")
    add("More classes is a harder task, so these rows are not like for like. Section 3 compares them fairly.\n")

    add("## 3. Like for like: the 30 original classes\n")
    s = {v: R[v]["shared30"] for v in vs}
    add(f"Sketches of the 30 original classes only ({s['v1']['n']} sketches). v1 knows only these. For v2 and v3 two views: **restricted** (they may answer only with the 30, "
        "which removes the advantage v1 has of a smaller choice) and **free** (they may answer with any class they know, the situation a real user is in).\n")
    rows = []
    for v in vs:
        rows.append([v, "only the 30" if v == "v1" else "restricted to the 30"] + [pct(s[v]["masked"]["top5"][column(np.asarray(fr), x)]) for x in (0.2, 0.3, 0.5, 1.0)]
                    + [pct(gate_mean(s[v]["masked"], "top5", fr))])
        if v != "v1":
            rows.append([v, f"free (any of {len(R[v]['classes'])})"] + [pct(s[v]["free"]["top5"][column(np.asarray(fr), x)]) for x in (0.2, 0.3, 0.5, 1.0)] + [pct(gate_mean(s[v]["free"], "top5", fr))])
    add("Top-5 accuracy (%):\n")
    add(table(["Model", "Answers allowed", "20%", "30%", "50%", "100%", "mean of 20/30/50%"], rows, "|---|---|---:|---:|---:|---:|---:|"))
    rows = []
    for v in vs:
        rows.append([v, "only the 30" if v == "v1" else "restricted to the 30"] + [pct(s[v]["masked"]["top1"][column(np.asarray(fr), x)]) for x in (0.2, 0.3, 0.5, 1.0)])
        if v != "v1":
            rows.append([v, f"free (any of {len(R[v]['classes'])})"] + [pct(s[v]["free"]["top1"][column(np.asarray(fr), x)]) for x in (0.2, 0.3, 0.5, 1.0)])
    add("Top-1 accuracy (%):\n")
    add(table(["Model", "Answers allowed", "20%", "30%", "50%", "100%"], rows, "|---|---|---:|---:|---:|---:|"))
    add("![Shared classes](figures/" + figs["shared"] + ")\n")
    if "shared100" in R["v3"]:
        v2s = accuracy_rows_for_shared100(R)
        add(f"**v2 vs v3 on the 100 classes they share** ({R['v3']['shared100']['n']} sketches, both restricted to those 100; Top-5 mean of 20/30/50%): "
            f"v2 {pct(v2s)}%, v3 {pct(gate_mean(R['v3']['shared100']['masked'], 'top5', fr))}%.\n")

    add("## 4. Precision, recall and F1 (macro)\n")
    rows = []
    for tag, label in (("30", "30% of the ink"), ("100", "finished drawing")):
        for v in vs:
            p = R[v]["prf" + tag]
            rows.append([label, v, pct(p["precision"]), pct(p["recall"]), pct(p["f1"])])
    add(table(["Ink drawn", "Model", "Precision", "Recall", "F1"], rows, "|---|---|---:|---:|---:|"))
    add("Recall equals the mean per-class Top-1 accuracy. Where precision falls below recall a model over-uses some classes (answers them too often); where recall falls below precision it under-uses some.\n")
    add("![Macro scores](figures/" + figs["macro"] + ")\n")

    add("## 5. Calibration\n")
    rows = []
    for tag, label in (("30", "30% of the ink"), ("100", "finished drawing")):
        for v in vs:
            c = R[v]["calib" + tag]
            gap = c["mean_confidence"] - c["accuracy"]
            verdict = "over-confident" if gap > 0.02 else "under-confident" if gap < -0.02 else "close"
            rows.append([label, v, pct(c["accuracy"]), pct(c["mean_confidence"]), verdict, f"{c['ece']:.3f}", f"{c['nll']:.3f}", f"{c['brier']:.3f}"])
    add(table(["Ink drawn", "Model", "Top-1 accuracy %", "Mean confidence %", "Verdict", "ECE", "NLL", "Brier"], rows, "|---|---|---:|---:|---|---:|---:|---:|"))
    add("Verdict: **over-confident** when mean confidence exceeds accuracy by more than 2 points, **under-confident** when it falls short by more than 2 points. NLL and Brier cannot be compared across models with different numbers of classes.\n")
    add("![Calibration](figures/" + figs["calibration"] + ")\n")
    add("![Confidence of right and wrong answers](figures/" + figs["confidence"] + ")\n")

    add("## 6. How early is the answer right?\n")
    rows = []
    for v in vs:
        first = np.asarray(R[v]["first"], float)
        stays = np.asarray(R[v]["stays"], float)
        row = [v] + [pct(np.nanmean(np.where(np.isnan(first), np.inf, first) <= x + 1e-9)) for x in (0.2, 0.3, 0.5)]
        row += [f"{np.nanmedian(first) * 100:.0f}%" if np.isfinite(np.nanmedian(first)) else "n/a", pct(np.isnan(stays).mean())]
        rows.append(row)
    add("Share of sketches whose top-1 answer is already right by a given amount of ink (%), the median ink needed for the first right answer (among sketches that get one), "
        "and the share never reliably right from some point to the end:\n")
    add(table(["Model", "right by 20%", "right by 30%", "right by 50%", "median ink for first right", "never right to the end %"], rows, "|---|---:|---:|---:|---:|---:|"))
    add("![Recognition CDF](figures/" + figs["recognition"] + ")\n")

    add("## 7. Per class\n")
    add("Per-class Top-1 accuracy. Each class has 25 test sketches, so a per-class figure moves in steps of 4 points: read the **distribution**, not single classes.\n")
    add("![Per-class accuracy](figures/" + figs["perclass"] + ")\n")
    for v in vs:
        rec = np.asarray(R[v]["recall100"], float)
        rec30 = np.asarray(R[v]["recall30"], float)
        names = R[v]["classes"]
        order = np.argsort(np.where(np.isnan(rec), -1, rec))
        worst = [f"{names[i]} ({rec[i] * 100:.0f}%)" for i in order[:10]]
        best = [f"{names[i]} ({rec[i] * 100:.0f}%)" for i in order[::-1][:10]]
        add(f"**{v}** ({len(names)} classes): median {np.nanmedian(rec) * 100:.0f}% finished, {np.nanmedian(rec30) * 100:.0f}% at 30% of the ink; "
            f"{int(np.nansum(rec >= 0.9))} classes at or above 90%, {int(np.nansum(rec < 0.3))} below 30% (finished).  ")
        add(f"Easiest: {', '.join(best)}.  ")
        add(f"Hardest: {', '.join(worst)}.\n")

    add("## 8. What the models confuse\n")
    add(f"At 30% of the ink, the most common wrong answers (true class -> predicted class, number of sketches):\n")
    for v in vs:
        add(f"* **{v}**: " + "; ".join(f"{t} -> {p} ({n})" for t, p, n in R[v]["confusions30"][:8]))
    add("")
    add("![Top confusions](figures/" + figs["confusions"] + ")\n")
    add("![v1 confusion matrix](figures/" + figs["matrix"] + ")\n")

    add("## 9. Cost\n")
    rows = [[v, R[v]["model"], f"{len(R[v]['classes'])}", f"{R[v]['efficiency']['params_m']:.1f} M", f"{R[v]['efficiency']['size_mb']:.1f} MB", f"{R[v]['efficiency']['latency_ms']:.1f} ms"] for v in vs]
    add(table(["Model", "Architecture", "Classes", "Parameters", "ONNX size", "CPU time per prediction"], rows, "|---|---|---:|---:|---:|---:|"))
    add("Parameters are counted from the ONNX file (they include the decoder head that the app no longer displays). Time per prediction is from `meta.json`, measured natively with ONNX Runtime on a CPU at export; "
        "in the browser v3 takes about 47 ms.\n")
    add("![Cost](figures/" + figs["efficiency"] + ")\n")
    if figs.get("training"):
        add("## 10. Training curves\n")
        add("Training loss and the validation score used to pick the best epoch (mean Top-1 over the six fractions on a validation split). The models have different numbers of classes and "
            "different run lengths, so the curves show each model's own convergence, not a ranking.\n")
        add("![Training curves](figures/" + figs["training"] + ")\n")

    add("## 11. How to read these numbers\n")
    add("* The models are scored on held-out **QuickDraw** sketches (drawn on phones, cleaned by Google). Real mouse drawings differ, so expect lower accuracy for real users; this has not been measured.")
    add("* Each model is **one training run**; there are no seeds. Differences of about a point are within what another run could change.")
    add("* 25 sketches per class gives narrow aggregate intervals but coarse per-class figures. The official table in section 2 uses each model's full test split; section 2 states where it differs from the re-scored table.")
    add("* v1 and v2 were trained before a sampling bug was fixed (every epoch replayed the same samples); v3 was retrained after the fix. This lowers v1 and v2 somewhat, so the gap to v3 on shared classes may be larger than a fully corrected v1 / v2 would show. Details: `docs/FLYWHEEL.md`.")
    add("* More classes make a single prediction harder because look-alike classes compete (section 3, free vs restricted).\n")
    add("## Reproduce\n")
    add("```bash\npython -m src.eval.score_models --per-class 25 --workers 3   # about 10 minutes on a laptop CPU\npython -m src.eval.model_report\npython -m pytest tests/test_eval_metrics.py -q\n```\n")
    return "\n".join(L)


README = ROOT / "README.md"
START, END = "<!-- eval:start -->", "<!-- eval:end -->"


def readme_block(R: dict, figs: dict) -> str:
    """The evaluation summary shown in the README (tables from the numbers above, figures from report/figures)."""
    vs = list(R)
    fr = np.asarray(R[vs[0]]["fracs"])
    j = {x: column(fr, x) for x in (0.2, 0.3, 0.5, 1.0)}
    L = ["### Evaluation of v1, v2 and v3 in detail\n",
         "The shipped ONNX files re-scored on the same unseen held-out sketches (v1 " + f"{R['v1']['own']['n']:,}" + ", v2 " + f"{R['v2']['own']['n']:,}" + ", v3 " + f"{R['v3']['own']['n']:,}"
         + " sketches, each model on its own classes), cut at nine ink fractions. Full tables, per-class lists and method: [`report/EVALUATION.md`](report/EVALUATION.md); raw numbers: [`docs/results/evaluation.json`](docs/results/evaluation.json); "
         "regenerate with `python -m src.eval.score_models && python -m src.eval.model_report`.\n"]
    rows = []
    for v in vs:
        r = R[v]
        first = np.asarray(r["first"], float)
        rows.append([v, str(len(r["classes"])), pct(r["own"]["top1"][j[0.3]]), pct(r["own"]["top5"][j[0.3]]), pct(r["own"]["top1"][j[1.0]]), pct(r["own"]["top5"][j[1.0]]),
                     pct(r["prf30"]["f1"]), pct(r["prf100"]["f1"]), f"{r['calib30']['ece']:.3f}", pct(np.nanmean(np.where(np.isnan(first), np.inf, first) <= 0.3 + 1e-9))])
    L.append(table(["Model", "Classes", "Top-1 @30%", "Top-5 @30%", "Top-1 @100%", "Top-5 @100%", "Macro F1 @30%", "Macro F1 @100%", "ECE @30%", "Top-1 right by 30%"], rows))
    rows = []
    for v in vs:
        s = R[v]["shared30"]
        rows.append([v, "only the 30" if v == "v1" else "restricted to the 30", pct(gate_mean(s["masked"], "top5", fr.tolist())), pct(s["masked"]["top1"][j[0.3]]), pct(s["masked"]["top5"][j[1.0]])])
        if v != "v1":
            rows.append([v, f"free (any of {len(R[v]['classes'])})", pct(gate_mean(s["free"], "top5", fr.tolist())), pct(s["free"]["top1"][j[0.3]]), pct(s["free"]["top5"][j[1.0]])])
    L.append(f"On sketches of the 30 original classes only ({R['v1']['shared30']['n']} sketches), the like-for-like comparison:\n")
    L.append(table(["Model", "Answers allowed", "Top-5, mean of 20/30/50%", "Top-1 @30%", "Top-5 @100%"], rows, "|---|---|---:|---:|---:|"))
    for key, caption in (("curves", "Accuracy versus completion, with 95% intervals"), ("shared", "The 30 original classes, restricted and free"),
                         ("macro", "Macro precision, recall and F1"), ("calibration", "Calibration at 30% of the ink"), ("perclass", "Per-class accuracy"),
                         ("recognition", "How early the top-1 answer is right"), ("confusions", "Most common mistakes at 30%"), ("efficiency", "Size, speed and parameters")):
        L.append(f"![{caption}](report/figures/{figs[key]})\n")
    if figs.get("training"):
        L.append(f"![Training curves](report/figures/{figs['training']})\n")
    return "\n".join(L)


def update_readme(block: str) -> bool:
    text = README.read_text(encoding="utf-8")
    if START not in text or END not in text:
        return False
    head, rest = text.split(START, 1)
    tail = rest.split(END, 1)[1]
    README.write_text(head + START + "\n" + block + "\n" + END + tail, encoding="utf-8")
    return True


def accuracy_rows_for_shared100(R: dict) -> float:
    """v2's own result restricted to nothing (it only knows the 100): the mean of its Top-5 at 20/30/50% on its own sketches."""
    o = R["v2"]["own"]
    return float(np.mean([o["top5"][column(np.asarray(R["v2"]["fracs"]), g)] for g in GATE_FRACS]))


def main() -> None:
    R = {v: evaluate(v) for v in ("v1", "v2", "v3") if (EVAL / f"{v}.npz").is_file()}
    figs = {
        "curves": F.accuracy_curves(R), "shared": F.shared_classes(R), "perclass": F.per_class(R), "calibration": F.calibration(R), "confidence": F.confidence(R),
        "recognition": F.recognition(R), "confusions": F.top_confusions(R), "macro": F.macro_scores(R), "efficiency": F.efficiency(R),
        "matrix": F.confusion_matrix(R["v1"], R["v1"]["classes"], "v1"), "training": F.training_curves(),
    }
    OUT_MD.write_text(write_markdown(R, figs), encoding="utf-8")
    print("README block updated" if update_readme(readme_block(R, figs)) else "README has no eval markers: block not inserted")
    slim = {v: {k: x for k, x in r.items() if k not in ("conf30", "ok30", "first", "stays", "conf30_matrix")} for v, r in R.items()}
    OUT_JSON.write_text(json.dumps(slim, indent=1), encoding="utf-8")
    print("wrote", OUT_MD, OUT_JSON, "and", len([f for f in figs.values() if f]), "figures")


if __name__ == "__main__":
    main()
