"""Module I experiments with the from-scratch NumPy MLP.

python -m src.train.mlp_baseline mnist     # digit classification warm-up
python -m src.train.mlp_baseline sketch    # baseline accuracy-vs-completion on partial sketches
"""
import json
import sys

import numpy as np
import torch
import torch.nn.functional as F
from torch.utils.data import DataLoader

from src.common import NUM_CLASSES, PROC_DIR, RUNS_DIR
from src.data.dataset import PartialSketchTrain, eval_set, load_splits
from src.models.mlp_numpy import MLP


def mnist():
    import torchvision

    root = PROC_DIR / "mnist"
    tr = torchvision.datasets.MNIST(root, train=True, download=True)
    te = torchvision.datasets.MNIST(root, train=False, download=True)
    X, y = tr.data.numpy().reshape(-1, 784).astype(np.float32) / 255, tr.targets.numpy()
    Xt, yt = te.data.numpy().reshape(-1, 784).astype(np.float32) / 255, te.targets.numpy()
    net = MLP([784, 256, 128, 10], lr=0.05)
    a, n = net.grad_check(X[:32], y[:32])
    print("grad check (analytic vs numeric):", np.round(a, 5), np.round(n, 5), "max diff", float(np.abs(a - n).max()))
    net.fit(X, y, epochs=12, on_epoch=lambda e, l: print(f"epoch {e} loss {l:.4f} test acc {net.accuracy(Xt, yt):.4f}", flush=True))
    out = RUNS_DIR / "mlp_mnist"
    out.mkdir(parents=True, exist_ok=True)
    json.dump({"test_acc": net.accuracy(Xt, yt)}, open(out / "results.json", "w"))


def sketch(n_train: int = 60000):
    sk, lb = load_splits()["train"]
    dl = DataLoader(PartialSketchTrain(sk, lb, n_train), batch_size=500, num_workers=6)
    Xs, ys = [], []
    for b in dl:
        Xs.append(F.avg_pool2d(b["img"], 2).flatten(1).numpy())
        ys.append(b["y"].numpy())
    X, y = np.concatenate(Xs), np.concatenate(ys)
    net = MLP([1024, 512, 256, NUM_CLASSES], lr=0.03)
    net.fit(X, y, epochs=15, on_epoch=lambda e, l: print(f"epoch {e} loss {l:.4f}", flush=True))
    res = {}
    for frac, d in eval_set("test").items():
        Xt, yt = F.avg_pool2d(d["img"].float() / 255.0, 2).flatten(1).numpy(), d["y"].numpy()
        res[str(frac)] = {"top1": net.accuracy(Xt, yt), "top5": net.accuracy(Xt, yt, 5), "ghost_bce": None}
    out = RUNS_DIR / "mlp"
    out.mkdir(parents=True, exist_ok=True)
    json.dump(res, open(out / "results.json", "w"), indent=2)
    print({k: round(v["top5"], 3) for k, v in res.items()}, "(top5)")


if __name__ == "__main__":
    {"mnist": mnist, "sketch": sketch}[sys.argv[1]]()
