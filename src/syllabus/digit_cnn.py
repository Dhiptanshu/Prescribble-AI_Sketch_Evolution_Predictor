"""Module III: a CNN for handwritten-digit classification (MNIST), compared with the from-scratch NumPy MLP of Module I.

python -m src.syllabus.digit_cnn [--epochs 12] [--smoke]
Outputs runs/syllabus/digit_cnn/{model.pt, results.json} and report/figures/syllabus_digit_cnn.png
"""
import argparse
import json
import math
import time

import numpy as np
import torch
import torch.nn as nn
import torch.nn.functional as F

from src.common import RUNS_DIR
from src.syllabus.common import device, load_mnist, run_dir, save_figure, save_results, seed_all, style


def block(i: int, o: int) -> nn.Sequential:
    return nn.Sequential(nn.Conv2d(i, o, 3, padding=1, bias=False), nn.BatchNorm2d(o), nn.ReLU(inplace=True))


class DigitCNN(nn.Module):
    """Two conv blocks per resolution (28 -> 14 -> 7), then a small classifier. About 0.4 M parameters."""

    def __init__(self):
        super().__init__()
        self.body = nn.Sequential(block(1, 32), block(32, 32), nn.MaxPool2d(2), nn.Dropout(0.15),
                                  block(32, 64), block(64, 64), nn.MaxPool2d(2), nn.Dropout(0.15))
        self.head = nn.Sequential(nn.Flatten(), nn.Linear(64 * 7 * 7, 128), nn.ReLU(inplace=True), nn.Dropout(0.3), nn.Linear(128, 10))

    def forward(self, x):
        return self.head(self.body(x))


def random_affine(x: torch.Tensor, rot: float = 10, shift: float = 0.08, scale: float = 0.1) -> torch.Tensor:
    """Per-sample random rotation / translation / zoom for a whole batch at once (the only augmentation used)."""
    b = x.size(0)
    a = (torch.rand(b, device=x.device) * 2 - 1) * rot * math.pi / 180
    s = 1 + (torch.rand(b, device=x.device) * 2 - 1) * scale
    t = (torch.rand(b, 2, device=x.device) * 2 - 1) * shift * 2
    theta = torch.stack([torch.stack([s * a.cos(), -s * a.sin(), t[:, 0]], 1), torch.stack([s * a.sin(), s * a.cos(), t[:, 1]], 1)], 1)
    return F.grid_sample(x, F.affine_grid(theta, x.shape, align_corners=False), align_corners=False, padding_mode="zeros")


@torch.no_grad()
def predict(model: nn.Module, x: torch.Tensor, dev, bs: int = 1000) -> torch.Tensor:
    model.eval()
    return torch.cat([model(x[i:i + bs].to(dev)).cpu() for i in range(0, len(x), bs)])


def train(epochs: int, bs: int = 128, lr: float = 3e-3, augment: bool = True, limit: int | None = None, log=print):
    dev = device()
    seed_all(0)
    x, y = load_mnist(True, limit)
    xt, yt = load_mnist(False, limit)
    x, y = x.to(dev), y.to(dev)
    model = DigitCNN().to(dev)
    opt = torch.optim.AdamW(model.parameters(), lr=lr, weight_decay=1e-4)
    steps = epochs * math.ceil(len(x) / bs)
    sched = torch.optim.lr_scheduler.OneCycleLR(opt, max_lr=lr, total_steps=steps)
    history = []
    for ep in range(1, epochs + 1):
        model.train()
        perm, total, t0 = torch.randperm(len(x), device=dev), 0.0, time.time()
        for i in range(0, len(x), bs):
            idx = perm[i:i + bs]
            xb = random_affine(x[idx]) if augment else x[idx]
            loss = F.cross_entropy(model(xb), y[idx], label_smoothing=0.05)
            opt.zero_grad(set_to_none=True)
            loss.backward()
            opt.step()
            sched.step()
            total += loss.item() * len(idx)
        acc = (predict(model, xt, dev).argmax(1) == yt).float().mean().item()
        history.append({"epoch": ep, "train_loss": total / len(x), "test_acc": acc})
        log(f"epoch {ep:2d}  loss {total / len(x):.4f}  test acc {acc:.4f}  ({time.time() - t0:.0f}s)")
    return model.cpu(), history, (xt, yt)


def confusion(pred: np.ndarray, truth: np.ndarray) -> np.ndarray:
    m = np.zeros((10, 10), int)
    np.add.at(m, (truth, pred), 1)
    return m


def figure(m: np.ndarray, wrong: list[tuple[np.ndarray, int, int]], history: list[dict]):
    import matplotlib.pyplot as plt

    style()
    fig, axs = plt.subplots(1, 3, figsize=(15, 4.3), gridspec_kw={"width_ratios": [1.1, 1.1, 1]})
    off = m.copy()
    np.fill_diagonal(off, 0)
    axs[0].imshow(off, cmap="magma")
    axs[0].set(title="Confusion (errors only)", xlabel="predicted", ylabel="true", xticks=range(10), yticks=range(10))
    axs[0].grid(False)
    axs[1].plot([h["epoch"] for h in history], [h["test_acc"] * 100 for h in history], marker="o")
    axs[1].set(title="Test accuracy per epoch", xlabel="epoch", ylabel="%")
    axs[2].axis("off")
    axs[2].set_title("Some mistakes (true -> predicted)", fontsize=10)
    for k, (img, t, p) in enumerate(wrong[:12]):
        a = fig.add_axes([0.70 + (k % 4) * 0.075, 0.55 - (k // 4) * 0.2, 0.065, 0.17])
        a.imshow(img, cmap="gray")
        a.set_title(f"{t}->{p}", fontsize=9)
        a.axis("off")
    return fig


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--epochs", type=int, default=12)
    ap.add_argument("--smoke", action="store_true")
    a = ap.parse_args()
    smoke = a.smoke
    model, history, (xt, yt) = train(1 if smoke else a.epochs, limit=2000 if smoke else None)
    pred = predict(model, xt, "cpu").argmax(1).numpy()
    truth = yt.numpy()
    m = confusion(pred, truth)
    acc = float((pred == truth).mean())
    wrong = [(xt[i, 0].numpy(), int(truth[i]), int(pred[i])) for i in np.flatnonzero(pred != truth)]
    mlp = RUNS_DIR / "mlp_mnist" / "results.json"
    results = {
        "test_acc": acc, "errors": int((pred != truth).sum()), "test_size": int(len(truth)), "epochs": len(history),
        "params": sum(p.numel() for p in model.parameters()), "history": history,
        "per_class_acc": {str(c): float(m[c, c] / m[c].sum()) for c in range(10)},
        "numpy_mlp_acc": json.loads(mlp.read_text())["test_acc"] if mlp.exists() else None,
    }
    torch.save(model.state_dict(), run_dir("digit_cnn") / "model.pt")
    save_results("digit_cnn", results)
    if not smoke:
        save_figure(figure(m, wrong, history), "digit_cnn")
    print(f"test accuracy {acc:.4f} ({results['errors']} errors of {results['test_size']}); NumPy MLP: {results['numpy_mlp_acc']}")


if __name__ == "__main__":
    main()
