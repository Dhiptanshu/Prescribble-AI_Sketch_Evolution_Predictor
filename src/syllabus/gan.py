"""Module II: a DCGAN on MNIST, judged with the digit CNN.

No FID here (it needs ImageNet features that say little about digits). Instead the trained digit classifier scores the generated images:
  confidence  mean max-probability (are they recognisable digits?)
  coverage    entropy of the predicted-class histogram (do all ten digits appear? max = ln 10 = 2.303)
  score       exp(E[KL(p(y|x) || p(y))]), the Inception-Score formula with the digit CNN; 10 means sharp and perfectly diverse.
Real test images get the same numbers, so the reader can see the ceiling.

python -m src.syllabus.gan [--epochs 25] [--smoke]      (needs runs/syllabus/digit_cnn/model.pt from digit_cnn first)
Outputs runs/syllabus/gan/{generator.pt, results.json} and report/figures/syllabus_gan.png
"""
import argparse
import math
import time

import torch
import torch.nn as nn
import torch.nn.functional as F

from src.syllabus.common import SYLLABUS_RUNS, device, image_grid, load_mnist, run_dir, save_figure, save_results, seed_all, style
from src.syllabus.digit_cnn import DigitCNN, predict

ZDIM = 100


class Generator(nn.Module):
    def __init__(self):
        super().__init__()
        self.fc = nn.Sequential(nn.Linear(ZDIM, 128 * 7 * 7, bias=False), nn.BatchNorm1d(128 * 7 * 7), nn.ReLU(inplace=True))
        self.net = nn.Sequential(nn.ConvTranspose2d(128, 64, 4, 2, 1, bias=False), nn.BatchNorm2d(64), nn.ReLU(inplace=True),
                                 nn.ConvTranspose2d(64, 1, 4, 2, 1), nn.Tanh())

    def forward(self, z):
        return self.net(self.fc(z).view(-1, 128, 7, 7))          # in [-1, 1]


class Discriminator(nn.Module):
    def __init__(self):
        super().__init__()
        self.net = nn.Sequential(nn.Conv2d(1, 64, 4, 2, 1), nn.LeakyReLU(0.2, inplace=True),
                                 nn.Conv2d(64, 128, 4, 2, 1, bias=False), nn.BatchNorm2d(128), nn.LeakyReLU(0.2, inplace=True),
                                 nn.Flatten(), nn.Dropout(0.3), nn.Linear(128 * 49, 1))

    def forward(self, x):
        return self.net(x).squeeze(1)                              # a logit: > 0 means "real"


def to_unit(g_out: torch.Tensor) -> torch.Tensor:
    return (g_out + 1) / 2


def score_samples(images01: torch.Tensor, classifier: nn.Module, dev) -> dict:
    """The three numbers above for a batch of images in [0, 1]."""
    p = F.softmax(predict(classifier, images01, dev), 1)
    marginal = p.mean(0)
    entropy = float(-(marginal * marginal.clamp_min(1e-12).log()).sum())
    kl = (p * (p.clamp_min(1e-12).log() - marginal.clamp_min(1e-12).log())).sum(1).mean()
    return {"confidence": float(p.max(1).values.mean()), "class_entropy": entropy, "score": float(kl.exp()),
            "class_share": [round(float(v), 4) for v in marginal]}


def train(epochs: int, bs: int = 128, limit: int | None = None, snapshots=(1,), log=print):
    dev = device()
    seed_all(0)
    x, _ = load_mnist(True, limit)
    x = (x * 2 - 1).to(dev)
    g, d = Generator().to(dev), Discriminator().to(dev)
    og = torch.optim.Adam(g.parameters(), 2e-4, betas=(0.5, 0.999))
    od = torch.optim.Adam(d.parameters(), 2e-4, betas=(0.5, 0.999))
    fixed = torch.randn(64, ZDIM, device=dev)
    hist, snaps = [], {}
    for ep in range(1, epochs + 1):
        perm, t0, ld, lg = torch.randperm(len(x), device=dev), time.time(), 0.0, 0.0
        g.train(); d.train()
        for i in range(0, len(x) - bs + 1, bs):
            real = x[perm[i:i + bs]]
            fake = g(torch.randn(bs, ZDIM, device=dev))
            # discriminator: real -> 1 (smoothed to 0.9 so it does not become over-confident), fake -> 0
            loss_d = F.binary_cross_entropy_with_logits(d(real), torch.full((bs,), 0.9, device=dev)) + \
                F.binary_cross_entropy_with_logits(d(fake.detach()), torch.zeros(bs, device=dev))
            od.zero_grad(set_to_none=True); loss_d.backward(); od.step()
            # generator: the non-saturating loss, push D(fake) towards "real"
            loss_g = F.binary_cross_entropy_with_logits(d(fake), torch.ones(bs, device=dev))
            og.zero_grad(set_to_none=True); loss_g.backward(); og.step()
            ld, lg = ld + loss_d.item(), lg + loss_g.item()
        steps = len(x) // bs
        hist.append({"epoch": ep, "d_loss": ld / steps, "g_loss": lg / steps})
        log(f"epoch {ep:2d}  D {ld / steps:.3f}  G {lg / steps:.3f}  ({time.time() - t0:.0f}s)")
        if ep in snapshots or ep == epochs:
            g.eval()
            with torch.no_grad():
                snaps[ep] = to_unit(g(fixed)).cpu()
    return g.cpu().eval(), hist, snaps


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--epochs", type=int, default=25)
    ap.add_argument("--smoke", action="store_true")
    a = ap.parse_args()
    epochs, limit = (1, 2000) if a.smoke else (a.epochs, None)
    dev = device()

    clf_path = SYLLABUS_RUNS / "digit_cnn" / "model.pt"
    if not clf_path.exists():
        raise SystemExit("run `python -m src.syllabus.digit_cnn` first: the GAN is scored with that classifier")
    clf = DigitCNN()
    clf.load_state_dict(torch.load(clf_path, map_location="cpu"))
    clf = clf.to(dev)

    snapshot_epochs = sorted({1, max(1, epochs // 5), max(1, epochs // 2), epochs})
    g, hist, snaps = train(epochs, limit=limit, snapshots=snapshot_epochs)
    torch.manual_seed(7)
    with torch.no_grad():
        generated = to_unit(g(torch.randn(10000, ZDIM)))
    xt, _ = load_mnist(False, limit)
    results = {"epochs": epochs, "generated": score_samples(generated, clf, dev), "real_test": score_samples(xt, clf, dev),
               "noise_baseline": score_samples(torch.rand(2000, 1, 28, 28), clf, dev), "history": hist}
    torch.save(g.state_dict(), run_dir("gan") / "generator.pt")
    save_results("gan", results)
    if a.smoke:
        print({k: results[k] for k in ("generated", "real_test", "noise_baseline")})
        return

    import matplotlib.pyplot as plt

    style()
    fig = plt.figure(figsize=(15, 8.5))
    gs = fig.add_gridspec(2, len(snaps) + 1, height_ratios=[1.25, 1])
    for k, (ep, img) in enumerate(sorted(snaps.items())):
        image_grid(img, 8, fig.add_subplot(gs[0, k]), f"epoch {ep}: the same 64 noise vectors")
    ax = fig.add_subplot(gs[0, len(snaps)])
    image_grid(xt[:64], 8, ax, "real test digits")
    ax = fig.add_subplot(gs[1, :2])
    ax.plot([h["epoch"] for h in hist], [h["d_loss"] for h in hist], label="discriminator")
    ax.plot([h["epoch"] for h in hist], [h["g_loss"] for h in hist], label="generator")
    ax.set(xlabel="epoch", ylabel="loss", title="Adversarial training losses")
    ax.legend()
    ax = fig.add_subplot(gs[1, 2:])
    width = 0.27
    for k, (key, lab) in enumerate((("generated", "GAN samples"), ("real_test", "real digits"), ("noise_baseline", "random noise"))):
        ax.bar([i + (k - 1) * width for i in range(10)], results[key]["class_share"], width, label=lab)
    ax.set(xticks=range(10), xlabel="class predicted by the digit CNN", ylabel="share", title="Which digits does the GAN make? (mode coverage)")
    ax.legend(fontsize=8)
    fig.tight_layout()
    save_figure(fig, "gan")
    print({k: {m: round(v, 3) for m, v in results[k].items() if m != "class_share"} for k in ("generated", "real_test", "noise_baseline")})


if __name__ == "__main__":
    main()
