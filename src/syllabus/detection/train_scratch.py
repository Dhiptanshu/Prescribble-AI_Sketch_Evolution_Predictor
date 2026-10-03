"""Module III: train the from-scratch YOLO-style detector (yolo_lite.py) and evaluate it with our own mAP code.

python -m src.syllabus.detection.train_scratch [--epochs 40] [--train 20000] [--val 2000] [--smoke]
Outputs runs/syllabus/det_scratch/{model.pt, results.json} and report/figures/syllabus_det_scratch.png
"""
import argparse
import math
import time

import numpy as np
import torch

from src.syllabus.common import device, run_dir, save_figure, save_results, seed_all, style
from src.syllabus.detection import metrics
from src.syllabus.detection.scenes import SIZE, build_scenes
from src.syllabus.detection.yolo_lite import YoloLite, build_targets, predict, yolo_loss


def to_batch(imgs: np.ndarray, dev) -> torch.Tensor:
    return torch.from_numpy(imgs).float().div(255).unsqueeze(1).to(dev)


def score(model, imgs: np.ndarray, boxes: list[np.ndarray], dev, bs: int = 500) -> dict:
    preds = []
    for i in range(0, len(imgs), bs):
        preds += predict(model, to_batch(imgs[i:i + bs], dev))
    return metrics.evaluate(preds, boxes)


def train(epochs: int, n_train: int, n_val: int, bs: int = 64, lr: float = 3e-3, log=print):
    dev = device()
    seed_all(0)
    t0 = time.time()
    tr_img, tr_box = build_scenes(n_train, "train")
    va_img, va_box = build_scenes(n_val, "val")
    log(f"built {n_train} train and {n_val} validation scenes in {time.time() - t0:.0f}s")
    model = YoloLite().to(dev)
    opt = torch.optim.AdamW(model.parameters(), lr=lr, weight_decay=1e-4)
    sched = torch.optim.lr_scheduler.OneCycleLR(opt, max_lr=lr, total_steps=epochs * math.ceil(n_train / bs))
    hist = []
    for ep in range(1, epochs + 1):
        model.train()
        perm, t0, tot = np.random.default_rng(ep).permutation(n_train), time.time(), 0.0
        for i in range(0, n_train, bs):
            idx = perm[i:i + bs]
            x = to_batch(tr_img[idx], dev)
            obj, tbox, tcls = build_targets([tr_box[j] for j in idx], dev)
            loss, _ = yolo_loss(model(x), obj, tbox, tcls)
            opt.zero_grad(set_to_none=True)
            loss.backward()
            opt.step()
            sched.step()
            tot += loss.item() * len(idx)
        m = score(model, va_img[:500], va_box[:500], dev)
        hist.append({"epoch": ep, "loss": tot / n_train, "map50_val500": m["map50"]})
        log(f"epoch {ep:2d}  loss {tot / n_train:.3f}  mAP@0.5 (500 val scenes) {m['map50']:.3f}  ({time.time() - t0:.0f}s)")
    return model, hist, (va_img, va_box)


def figure(model, hist, final: dict, va_img, va_box, dev):
    import matplotlib.pyplot as plt
    from matplotlib.patches import Rectangle

    style()
    fig = plt.figure(figsize=(15, 8.6))
    gs = fig.add_gridspec(2, 6)
    ax = fig.add_subplot(gs[0, 0:2])
    ax.plot([h["epoch"] for h in hist], [h["loss"] for h in hist], color="C3")
    ax.set(xlabel="epoch", ylabel="training loss", title="Loss")
    ax = fig.add_subplot(gs[0, 2:4])
    ax.plot([h["epoch"] for h in hist], [h["map50_val500"] for h in hist], marker="o", color="C0")
    ax.set(xlabel="epoch", ylabel="mAP@0.5", ylim=(0, 1.02), title="Validation mAP@0.5 during training")
    ax = fig.add_subplot(gs[0, 4:6])
    ap = [v if v is not None else 0 for v in final["ap50_per_class"]]
    ax.bar(range(10), ap, color="C2")
    ax.set(xticks=range(10), xlabel="digit", ylabel="AP@0.5", ylim=(0, 1.02), title="Per-class AP@0.5")
    preds = predict(model, to_batch(va_img[:6], dev), conf=0.3)
    for k in range(6):
        ax = fig.add_subplot(gs[1, k])
        ax.imshow(va_img[k], cmap="gray", vmin=0, vmax=255)
        ax.axis("off")
        for c, x1, y1, x2, y2 in va_box[k]:
            ax.add_patch(Rectangle((x1, y1), x2 - x1, y2 - y1, fill=False, ec="#22c55e", lw=1.6))
        for c, s, x1, y1, x2, y2 in preds[k]:
            ax.add_patch(Rectangle((x1, y1), x2 - x1, y2 - y1, fill=False, ec="#ef4444", lw=1.2, ls="--"))
            ax.text(x1, max(8, y1 - 2), f"{int(c)} {s:.2f}", color="#ef4444", fontsize=8)
        ax.set_title("green = truth, red = prediction" if k == 0 else "", fontsize=8)
    fig.tight_layout()
    return fig


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--epochs", type=int, default=40)
    ap.add_argument("--train", type=int, default=20000)
    ap.add_argument("--val", type=int, default=2000)
    ap.add_argument("--smoke", action="store_true")
    a = ap.parse_args()
    epochs, n_train, n_val = (1, 300, 100) if a.smoke else (a.epochs, a.train, a.val)
    model, hist, (va_img, va_box) = train(epochs, n_train, n_val)
    dev = device()
    final = score(model, va_img, va_box, dev)
    results = {"detector": "YoloLite (from scratch)", "epochs": epochs, "train_scenes": n_train, "val_scenes": n_val,
               "params": sum(p.numel() for p in model.parameters()), "val_objects": int(sum(len(b) for b in va_box)), **final, "history": hist}
    torch.save(model.cpu().state_dict(), run_dir("det_scratch") / "model.pt")
    save_results("det_scratch", results)
    if not a.smoke:
        save_figure(figure(model.to(dev), hist, final, va_img, va_box, dev), "det_scratch")
    print(f"mAP@0.5 {final['map50']:.3f}   mAP@[0.5:0.95] {final['map50_95']:.3f}   ({results['val_objects']} objects in {n_val} scenes)")


if __name__ == "__main__":
    main()
