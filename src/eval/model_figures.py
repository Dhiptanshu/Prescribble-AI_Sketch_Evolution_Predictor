"""Figures for report/EVALUATION.md. Every plot is drawn from the numbers computed by src/eval/model_report.py; nothing is typed here."""
import csv
from pathlib import Path

import numpy as np

from src.common import ROOT

FIGURES = ROOT / "report" / "figures"
COLORS = {"v1": "#0ea5c6", "v2": "#e08a00", "v3": "#7c5cff"}
LOGS = {"v1": ROOT / "runs" / "fusion_ghost" / "log.csv", "v2": ROOT / "runs" / "v2" / "fusion_ghost" / "log.csv",
        "v3": ROOT / "runs" / "v3" / "fusion_ghost_xl" / "log.csv"}


def _plt():
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    plt.rcParams.update({"axes.grid": True, "grid.alpha": .25, "axes.spines.top": False, "axes.spines.right": False, "font.size": 10})
    return plt


def _save(fig, name: str) -> str:
    FIGURES.mkdir(parents=True, exist_ok=True)
    fig.tight_layout()
    fig.savefig(FIGURES / name, dpi=130)
    fig.clf()
    return name


def accuracy_curves(R: dict) -> str:
    plt = _plt()
    fig, axs = plt.subplots(1, 2, figsize=(12, 4.4))
    for ax, key, title in zip(axs, ("top1", "top5"), ("Top-1", "Top-5")):
        for v, r in R.items():
            x = np.asarray(r["fracs"]) * 100
            ax.plot(x, np.asarray(r["own"][key]) * 100, marker="o", color=COLORS[v], label=f"{v}: {len(r['classes'])} classes")
            ax.fill_between(x, np.asarray(r["own"][key + "_lo"]) * 100, np.asarray(r["own"][key + "_hi"]) * 100, color=COLORS[v], alpha=.15)
        ax.set(xlabel="% of the drawing's ink", ylabel=f"{title} accuracy (%)", title=f"{title} accuracy vs completion (own classes, 95% interval)")
        ax.legend()
    return _save(fig, "eval_accuracy_curves.png")


def shared_classes(R: dict) -> str:
    plt = _plt()
    fig, axs = plt.subplots(1, 2, figsize=(12, 4.4))
    for ax, key, title in zip(axs, ("top1", "top5"), ("Top-1", "Top-5")):
        for v, r in R.items():
            s = r["shared30"]
            x = np.asarray(r["fracs"]) * 100
            ax.plot(x, np.asarray(s["masked"][key]) * 100, marker="o", color=COLORS[v], label=f"{v}, may answer only the 30" if v != "v1" else "v1 (has only the 30)")
            if v != "v1":
                ax.plot(x, np.asarray(s["free"][key]) * 100, ls="--", marker="x", color=COLORS[v], label=f"{v}, may answer any of its {len(r['classes'])}")
        ax.set(xlabel="% of the drawing's ink", ylabel=f"{title} accuracy (%)", title=f"{title} on sketches of the 30 original classes")
        ax.legend(fontsize=8)
    return _save(fig, "eval_shared_classes.png")


def per_class(R: dict) -> str:
    plt = _plt()
    fig, axs = plt.subplots(2, len(R), figsize=(4.2 * len(R), 6.4), squeeze=False)
    for col, (v, r) in enumerate(R.items()):
        for row, (key, label) in enumerate((("recall30", "30% of the ink"), ("recall100", "finished drawing"))):
            vals = np.asarray(r[key])
            vals = vals[~np.isnan(vals)] * 100
            axs[row, col].hist(vals, bins=np.linspace(0, 100, 21), color=COLORS[v])
            axs[row, col].set(xlabel="per-class Top-1 accuracy (%)", ylabel="classes", title=f"{v}: {label}\nmedian {np.median(vals):.0f}%, mean {vals.mean():.0f}%")
    return _save(fig, "eval_per_class.png")


def calibration(R: dict) -> str:
    plt = _plt()
    fig, axs = plt.subplots(1, len(R), figsize=(4.2 * len(R), 4.2), squeeze=False)
    for ax, (v, r) in zip(axs[0], R.items()):
        c = r["calib30"]
        conf = [b["confidence"] for b in c["curve"]]
        acc = [b["accuracy"] for b in c["curve"]]
        size = np.asarray([b["count"] for b in c["curve"]], float)
        ax.plot([0, 1], [0, 1], color="#888", ls=":", label="perfectly calibrated")
        ax.plot(conf, acc, color=COLORS[v], marker="o", lw=1.5, zorder=2)
        ax.scatter(conf, acc, s=20 + 380 * size / size.max(), color=COLORS[v], alpha=.45, zorder=3)
        ax.set(xlabel="stated confidence (top-1)", ylabel="actual accuracy", xlim=(0, 1), ylim=(0, 1), title=f"{v} at 30% of the ink\nECE {c['ece']:.3f}")
        ax.legend(loc="upper left", fontsize=8)
    return _save(fig, "eval_calibration.png")


def confidence(R: dict) -> str:
    plt = _plt()
    fig, axs = plt.subplots(1, len(R), figsize=(4.2 * len(R), 3.8), squeeze=False)
    bins = np.linspace(0, 1, 21)
    for ax, (v, r) in zip(axs[0], R.items()):
        conf, ok = np.asarray(r["conf30"]), np.asarray(r["ok30"])
        ax.hist(conf[ok], bins=bins, alpha=.7, color="#16a34a", label=f"right ({ok.mean() * 100:.0f}%)")
        ax.hist(conf[~ok], bins=bins, alpha=.7, color="#dc2626", label=f"wrong ({(~ok).mean() * 100:.0f}%)")
        ax.set(xlabel="top-1 confidence", ylabel="sketches", title=f"{v} at 30% of the ink")
        ax.legend(fontsize=8)
    return _save(fig, "eval_confidence.png")


def recognition(R: dict) -> str:
    plt = _plt()
    fig, ax = plt.subplots(figsize=(6.4, 4.4))
    grid = np.linspace(0.1, 1.0, 91)
    for v, r in R.items():
        for key, style, label in (("first", "-", "first right"), ("stays", "--", "right from then on")):
            a = np.asarray(r[key], float)
            ax.plot(grid * 100, [np.nanmean(np.where(np.isnan(a), np.inf, a) <= g + 1e-9) * 100 for g in grid], style, color=COLORS[v], label=f"{v}, {label}")
    ax.set(xlabel="% of the drawing's ink", ylabel="share of sketches (%)", title="How early is the top-1 answer right? (own classes)")
    ax.legend(fontsize=8)
    return _save(fig, "eval_recognition_cdf.png")


def confusion_matrix(r: dict, classes: list[str], v: str = "v1") -> str:
    plt = _plt()
    m = np.asarray(r["conf30_matrix"], float)
    m = m / np.maximum(m.sum(1, keepdims=True), 1)
    fig, ax = plt.subplots(figsize=(8.6, 7.6))
    im = ax.imshow(m, cmap="magma_r", vmin=0, vmax=1)
    ax.set(xticks=range(len(classes)), yticks=range(len(classes)), xlabel="predicted", ylabel="true", title=f"{v}: where the top-1 answer goes at 30% of the ink (row-normalised)")
    ax.set_xticklabels(classes, rotation=90, fontsize=7)
    ax.set_yticklabels(classes, fontsize=7)
    ax.grid(False)
    fig.colorbar(im, ax=ax, fraction=.046)
    return _save(fig, f"eval_confusion_{v}.png")


def top_confusions(R: dict) -> str:
    plt = _plt()
    fig, axs = plt.subplots(1, len(R), figsize=(4.8 * len(R), 4.4), squeeze=False)
    for ax, (v, r) in zip(axs[0], R.items()):
        pairs = r["confusions30"][:10][::-1]
        ax.barh([f"{t} -> {p}" for t, p, _ in pairs], [c for _, _, c in pairs], color=COLORS[v])
        ax.set(xlabel="sketches", title=f"{v}: most common mistakes at 30%")
        ax.tick_params(axis="y", labelsize=8)
    return _save(fig, "eval_top_confusions.png")


def macro_scores(R: dict) -> str:
    plt = _plt()
    fig, axs = plt.subplots(1, 2, figsize=(11, 3.9), sharey=True)
    for ax, key, label in zip(axs, ("prf30", "prf100"), ("30% of the ink", "finished drawing")):
        w = 0.26
        for i, name in enumerate(("precision", "recall", "f1")):
            vals = [R[v][key][name] * 100 for v in R]
            bars = ax.bar(np.arange(len(R)) + (i - 1) * w, vals, w, label=name, color=["#64748b", "#0ea5c6", "#7c5cff"][i])
            ax.bar_label(bars, fmt="%.0f", fontsize=7)
        ax.set(xticks=range(len(R)), xticklabels=list(R), title=f"Macro precision / recall / F1, {label}", ylabel="%")
        ax.legend(fontsize=8)
    return _save(fig, "eval_macro_scores.png")


def training_curves() -> str | None:
    plt = _plt()
    logs = {}
    for v, p in LOGS.items():
        if Path(p).is_file():
            with open(p, newline="") as f:
                rows = list(csv.DictReader(f))
            logs[v] = ([int(r["epoch"]) for r in rows], [float(r["loss"]) for r in rows], [float(r["val_mean_top1"]) for r in rows])
    if not logs:
        return None
    fig, axs = plt.subplots(1, 2, figsize=(12, 4))
    for v, (ep, loss, val) in logs.items():
        axs[0].plot(ep, loss, color=COLORS[v], label=v)
        axs[1].plot(ep, [x * 100 for x in val], color=COLORS[v], label=v)
    axs[0].set(xlabel="epoch", ylabel="training loss", title="Training loss")
    axs[1].set(xlabel="epoch", ylabel="validation mean Top-1 over the six fractions (%)", title="Validation accuracy (model selection signal)")
    axs[0].legend()
    axs[1].legend()
    return _save(fig, "eval_training_curves.png")


def efficiency(R: dict) -> str:
    plt = _plt()
    fig, axs = plt.subplots(1, 3, figsize=(11, 3.4))
    for ax, key, label in zip(axs, ("size_mb", "latency_ms", "params_m"), ("ONNX file size (MB)", "CPU time per prediction (ms)", "parameters (millions)")):
        vals = [R[v]["efficiency"][key] for v in R]
        bars = ax.bar(list(R), vals, color=[COLORS[v] for v in R])
        ax.bar_label(bars, fmt="%.1f", fontsize=8)
        ax.set(title=label)
    return _save(fig, "eval_efficiency.png")
