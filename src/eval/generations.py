"""Compare the model generations (v1: 30 classes, v2: 100, v3: 345) from their own measured results. Writes report/GENERATIONS.md and two figures.

python -m src.eval.generations
Every number is read from models/<version>/meta.json (test results on each model's own held-out QuickDraw sketches) and docs/results/*.json
(the shared-class comparisons run by the registry gate). Nothing is typed here.
"""
import json

import numpy as np

from src.common import ROOT

MODELS = ROOT / "models"
RESULTS = ROOT / "docs" / "results"
FIGURES = ROOT / "report" / "figures"
FRACS = ["0.1", "0.2", "0.3", "0.5", "0.75", "1.0"]


def load_meta(version: str) -> dict | None:
    p = MODELS / version / "meta.json"
    return json.loads(p.read_text(encoding="utf-8")) if p.is_file() else None


def versions() -> dict[str, dict]:
    return {v: m for v in ("v1", "v2", "v3") if (m := load_meta(v))}


def curves(metas: dict[str, dict]):
    import matplotlib.pyplot as plt

    FIGURES.mkdir(parents=True, exist_ok=True)
    fig, axs = plt.subplots(1, 2, figsize=(12.5, 4.4))
    for v, m in metas.items():
        for ax, key in zip(axs, ("top5", "top1")):
            ax.plot([float(f) * 100 for f in FRACS], [m["test_results"][f][key] * 100 for f in FRACS], marker="o", label=f"{v}: {len(m['classes'])} classes")
    for ax, key in zip(axs, ("Top-5", "Top-1")):
        ax.set(xlabel="% of the drawing's ink", ylabel=f"{key} accuracy (%)", title=f"{key} accuracy vs completion (each model on its own classes)")
        ax.grid(alpha=.25)
        ax.legend()
    fig.tight_layout()
    fig.savefig(FIGURES / "generations_accuracy.png", dpi=130)


def per_class_view(version: str, meta: dict):
    """(figure written, table rows of best and worst classes) from the per-class Top-1 stored in the model's results."""
    import matplotlib.pyplot as plt

    r = meta["test_results"]
    fin, early = r["1.0"].get("per_class_top1"), r["0.3"].get("per_class_top1")
    if not fin or not early:
        return None
    classes = meta["classes"]
    fig, axs = plt.subplots(1, 2, figsize=(12.5, 4))
    for ax, vals, title in ((axs[0], early, "at 30% of the ink"), (axs[1], fin, "on the finished drawing")):
        ax.hist([v * 100 for v in vals if v is not None], bins=20, color="#7c5cff")
        ax.set(xlabel="per-class Top-1 accuracy (%)", ylabel="number of classes", title=f"{version}: how well each of {len(classes)} classes is recognised, {title}")
        ax.title.set_fontsize(9.5)
        ax.grid(alpha=.25)
    fig.tight_layout()
    fig.savefig(FIGURES / f"{version}_per_class.png", dpi=130)
    ranked = sorted(((c, f, e) for c, f, e in zip(classes, fin, early) if f is not None), key=lambda t: -t[1])
    return ranked


def table(rows, title: str) -> str:
    return f"**{title}**\n\n| Class | Top-1 finished | Top-1 at 30% |\n|---|---:|---:|\n" + "\n".join(f"| {c} | {f * 100:.1f} | {e * 100:.1f} |" for c, f, e in rows)


def build() -> str:
    metas = versions()
    curves(metas)
    head = "| Model | Classes | Top-5 at 20% | Top-5 at 30% | Top-5 finished | Top-1 at 30% | Top-1 finished | Size | Latency (CPU) |\n|---|---:|---:|---:|---:|---:|---:|---:|---:|\n"
    rows = []
    for v, m in metas.items():
        r = m["test_results"]
        rows.append(f"| {v} ({m['model']}) | {len(m['classes'])} | {r['0.2']['top5'] * 100:.1f} | {r['0.3']['top5'] * 100:.1f} | {r['1.0']['top5'] * 100:.1f} | "
                    f"{r['0.3']['top1'] * 100:.1f} | {r['1.0']['top1'] * 100:.1f} | {m['size_mb']:.0f} MB | {m['latency_ms']:.1f} ms |")
    out = ["# Model generations\n", "Each model is measured on held-out QuickDraw sketches of **its own** classes, so the rows are not like for like: more classes is a harder task. "
           "The like-for-like comparison on shared classes follows.\n", head + "\n".join(rows) + "\n", "![accuracy vs completion](figures/generations_accuracy.png)\n"]
    for f in sorted(RESULTS.glob("gate_*.json")):
        v = json.loads(f.read_text(encoding="utf-8"))["comparison"]["verdict"]["quickdraw"]
        name = f.stem.replace("gate_", "").replace("_to_", " to ")
        out.append(f"**Shared-class comparison, {name}** ({v['n']} held-out sketches, both models limited to the classes they share, Top-5 averaged over 20 / 30 / 50% of the ink): "
                   f"live model {v['active_top5'] * 100:.1f}%, candidate {v['candidate_top5'] * 100:.1f}% (difference {v['delta'] * 100:+.1f} points); the candidate choosing among all its own classes: {v['candidate_unmasked_top5'] * 100:.1f}%.\n")
    latest = list(metas)[-1]
    ranked = per_class_view(latest, metas[latest])
    if ranked:
        out += [f"## {latest}: which classes work\n", f"![per class](figures/{latest}_per_class.png)\n", table(ranked[:12], "Easiest classes") + "\n", table(ranked[-12:][::-1], "Hardest classes") + "\n"]
        vals = np.array([f for _, f, _ in ranked])
        out.append(f"{int((vals >= 0.9).sum())} of {len(vals)} classes reach 90% Top-1 on the finished drawing, {int((vals >= 0.5).sum())} reach 50%, and {int((vals < 0.3).sum())} stay below 30%.\n")
    return "\n".join(out)


if __name__ == "__main__":
    (ROOT / "report" / "GENERATIONS.md").write_text(build(), encoding="utf-8")
    print("wrote report/GENERATIONS.md")
