"""Figures + numbers for the report, all computed from real runs and the held-out test set.

python -m src.eval.analysis
Writes report/figures/*.png and report/analysis.json
"""
import csv
import json

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import torch

from src.common import CLASSES, ROOT, RUNS_DIR
from src.data.dataset import as_float, eval_set
from src.models.nets import build

FIG = ROOT / "report" / "figures"
MODELS = ["mlp", "cnn", "lstm", "fusion", "fusion_ghost", "resnet_ghost"]
NAMES = {"mlp": "MLP (NumPy)", "cnn": "CNN", "lstm": "LSTM", "fusion": "CNN+LSTM", "fusion_ghost": "CNN+LSTM+ghost", "resnet_ghost": "ResNet18+LSTM+ghost"}
plt.rcParams.update({"figure.dpi": 130, "axes.spines.top": False, "axes.spines.right": False, "axes.grid": True, "grid.alpha": .25})


def results(m):
    return json.load(open(RUNS_DIR / m / "results.json"))


def accuracy_curves():
    for metric in ("top5", "top1"):
        fig, ax = plt.subplots(figsize=(7, 4.2))
        for m in MODELS:
            r = results(m)
            xs = sorted(r, key=float)
            ax.plot([float(x) * 100 for x in xs], [r[x][metric] * 100 for x in xs], marker="o", lw=2.4 if m == "fusion_ghost" else 1.6, label=NAMES[m])
        ax.axvspan(20, 30, color="#7c5cff", alpha=.08)
        ax.set(xlabel="% of the sketch's ink drawn", ylabel=f"{metric.replace('top', 'Top-')} accuracy (%)", title=f"Recognition from partial sketches ({metric})")
        ax.legend(frameon=False)
        fig.tight_layout(); fig.savefig(FIG / f"accuracy_vs_completion_{metric}.png"); plt.close(fig)


def training_curves():
    fig, ax = plt.subplots(1, 2, figsize=(10, 3.8))
    for m in MODELS[1:]:
        rows = list(csv.DictReader(open(RUNS_DIR / m / "log.csv")))
        ep = [int(r["epoch"]) for r in rows]
        ax[0].plot(ep, [float(r["loss"]) for r in rows], label=NAMES[m])
        ax[1].plot(ep, [float(r["val_mean_top1"]) * 100 for r in rows], label=NAMES[m])
    ax[0].set(title="Training loss", xlabel="epoch"); ax[1].set(title="Validation top-1 (mean over completion levels)", xlabel="epoch", ylabel="%")
    ax[1].legend(frameon=False, fontsize=8)
    fig.tight_layout(); fig.savefig(FIG / "training_curves.png"); plt.close(fig)


@torch.no_grad()
def model_analysis(frac=0.3):
    net = build("fusion_ghost")
    net.load_state_dict(torch.load(RUNS_DIR / "fusion_ghost" / "best.pt", map_location="cpu"))
    net.eval()
    data = eval_set("test")
    out = {}
    for f in (frac, 1.0):
        d = data[f]; preds, ghosts = [], []
        for i in range(0, len(d["y"]), 500):
            b = as_float({k: v[i : i + 500] for k, v in d.items()})
            lg, rc = net(b["img"], b["seq"], b["len"])
            preds.append(lg.argmax(1)); ghosts.append(torch.sigmoid(rc))
        out[f] = (torch.cat(preds).numpy(), torch.cat(ghosts), d)
    y = out[frac][2]["y"].numpy()
    p = out[frac][0]
    n = len(CLASSES)
    cm = np.zeros((n, n), int)
    np.add.at(cm, (y, p), 1)
    per_class = {f: [float((out[f][0][y == c] == c).mean()) for c in range(n)] for f in (frac, 1.0)}

    # per-class early vs final accuracy
    order = np.argsort(per_class[frac])
    fig, ax = plt.subplots(figsize=(8, 7))
    yy = np.arange(n)
    ax.barh(yy + .2, [per_class[1.0][i] * 100 for i in order], .4, label="100% of ink", color="#bbb")
    ax.barh(yy - .2, [per_class[frac][i] * 100 for i in order], .4, label=f"{int(frac * 100)}% of ink", color="#7c5cff")
    ax.set_yticks(yy, [CLASSES[i] for i in order]); ax.set(xlabel="Top-1 accuracy (%)", title="Which objects are recognised early?")
    ax.legend(frameon=False, loc="lower right")
    fig.tight_layout(); fig.savefig(FIG / "per_class_early_vs_final.png"); plt.close(fig)

    fig, ax = plt.subplots(figsize=(8.5, 7.5))
    ax.imshow(cm / cm.sum(1, keepdims=True), cmap="magma"); ax.grid(False)
    ax.set_xticks(range(n), CLASSES, rotation=90, fontsize=7); ax.set_yticks(range(n), CLASSES, fontsize=7)
    ax.set(xlabel="predicted", ylabel="true", title=f"Confusion at {int(frac * 100)}% of the ink")
    fig.tight_layout(); fig.savefig(FIG / "confusion_30.png"); plt.close(fig)

    pairs = sorted(((int(cm[i, j]), CLASSES[i], CLASSES[j]) for i in range(n) for j in range(n) if i != j), reverse=True)[:10]

    # ghost gallery: partial | model's ghost | full drawing
    d = out[frac][2]; g = out[frac][1]
    rng = np.random.default_rng(3)
    idx = [int(rng.choice(np.flatnonzero(y == c))) for c in rng.choice(n, 8, replace=False)]
    fig, ax = plt.subplots(3, 8, figsize=(12, 4.8))
    for k, i in enumerate(idx):
        ax[0, k].imshow(d["img"][i, 0], cmap="gray"); ax[1, k].imshow(g[i, 0], cmap="magma"); ax[2, k].imshow(d["target"][i, 0], cmap="gray")
        ax[0, k].set_title(CLASSES[y[i]], fontsize=9)
        for r in range(3):
            ax[r, k].axis("off")
    for r, t in enumerate(["30% drawn", "model's ghost", "actual full sketch"]):
        ax[r, 0].text(-0.1, .5, t, transform=ax[r, 0].transAxes, rotation=90, ha="right", va="center", fontsize=9)
    fig.tight_layout(); fig.savefig(FIG / "ghost_gallery.png"); plt.close(fig)
    return {"per_class_top1_30": dict(zip(CLASSES, per_class[frac])), "per_class_top1_100": dict(zip(CLASSES, per_class[1.0])),
            "top_confusions_at_30": [{"count": c, "true": a, "predicted": b} for c, a, b in pairs]}


def main():
    FIG.mkdir(parents=True, exist_ok=True)
    accuracy_curves(); training_curves()
    info = model_analysis()
    info["mnist_mlp_test_acc"] = json.load(open(RUNS_DIR / "mlp_mnist" / "results.json"))["test_acc"]
    sp = RUNS_DIR / "sentiment" / "results.json"
    if sp.exists():
        info["sentiment_lstm"] = json.load(open(sp))
    json.dump(info, open(ROOT / "report" / "analysis.json", "w"), indent=2)
    print("figures + analysis written")


if __name__ == "__main__":
    main()
