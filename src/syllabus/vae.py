"""Module II: a variational autoencoder (VAE) on MNIST.

Studies: the evidence lower bound (ELBO) with a 16-d latent, the learned 2-d manifold, and the beta trade-off (reconstruction vs KL).
python -m src.syllabus.vae [--epochs 12] [--smoke]
Outputs runs/syllabus/vae/{results.json, vae_*.pt} and report/figures/syllabus_vae.png
"""
import argparse
import math
import time

import torch
import torch.nn as nn
import torch.nn.functional as F

from src.syllabus.common import device, image_grid, load_mnist, run_dir, save_figure, save_results, seed_all, style


class ConvVAE(nn.Module):
    """Encoder -> (mu, log variance) -> z = mu + sigma * eps -> decoder (logits). The reparameterisation keeps sampling differentiable."""

    def __init__(self, latent: int):
        super().__init__()
        self.latent = latent
        self.enc = nn.Sequential(nn.Conv2d(1, 32, 3, 2, 1), nn.ReLU(inplace=True), nn.Conv2d(32, 64, 3, 2, 1), nn.ReLU(inplace=True), nn.Flatten())
        self.mu, self.logvar = nn.Linear(64 * 49, latent), nn.Linear(64 * 49, latent)
        self.dec_fc = nn.Sequential(nn.Linear(latent, 64 * 49), nn.ReLU(inplace=True))
        self.dec = nn.Sequential(nn.ConvTranspose2d(64, 32, 3, 2, 1, output_padding=1), nn.ReLU(inplace=True),
                                 nn.ConvTranspose2d(32, 1, 3, 2, 1, output_padding=1))

    def encode(self, x):
        h = self.enc(x)
        return self.mu(h), self.logvar(h)

    def decode(self, z):
        return self.dec(self.dec_fc(z).view(-1, 64, 7, 7))

    def forward(self, x):
        mu, logvar = self.encode(x)
        z = mu + torch.randn_like(mu) * torch.exp(0.5 * logvar)
        return self.decode(z), mu, logvar


def loss_terms(logits, x, mu, logvar):
    """Per-image reconstruction (BCE summed over pixels, nats) and KL(q(z|x) || N(0, I)) (nats), averaged over the batch."""
    recon = F.binary_cross_entropy_with_logits(logits, x, reduction="sum") / x.size(0)
    kl = -0.5 * torch.sum(1 + logvar - mu.pow(2) - logvar.exp()) / x.size(0)
    return recon, kl


@torch.no_grad()
def evaluate(model: ConvVAE, xt: torch.Tensor) -> dict:
    """Held-out negative ELBO (= recon + KL, lower is better), its two parts, and the number of 'active' latent dimensions."""
    model.eval()
    dev = next(model.parameters()).device
    torch.manual_seed(5)                                          # the same sampling noise for every evaluation
    recon = kl = 0.0
    mus = []
    for i in range(0, len(xt), 1000):
        xb = xt[i:i + 1000].to(dev)
        logits, mu, logvar = model(xb)
        r, k = loss_terms(logits, xb, mu, logvar)
        recon += r.item() * len(xb)
        kl += k.item() * len(xb)
        mus.append(mu.cpu())
    n = len(xt)
    active = int((torch.cat(mus).var(0) > 0.01).sum())          # a dimension is used if its mean code varies across images
    return {"recon": recon / n, "kl": kl / n, "neg_elbo": (recon + kl) / n, "active_dims": active}


def train(latent: int, epochs: int, beta: float = 1.0, bs: int = 128, limit: int | None = None, log=print):
    dev = device()
    seed_all(latent)
    x, _ = load_mnist(True, limit)
    xt, _ = load_mnist(False, limit)
    x = x.to(dev)
    model = ConvVAE(latent).to(dev)
    opt = torch.optim.Adam(model.parameters(), lr=1e-3)
    hist = []
    for ep in range(1, epochs + 1):
        model.train()
        perm, t0 = torch.randperm(len(x), device=dev), time.time()
        for i in range(0, len(x), bs):
            xb = x[perm[i:i + bs]]
            logits, mu, logvar = model(xb)
            recon, kl = loss_terms(logits, xb, mu, logvar)
            loss = recon + beta * kl
            opt.zero_grad(set_to_none=True)
            loss.backward()
            opt.step()
        hist.append(evaluate(model, xt.to(dev)))
        log(f"z={latent:2d} beta={beta}  epoch {ep:2d}  -ELBO {hist[-1]['neg_elbo']:.2f}  recon {hist[-1]['recon']:.2f}  KL {hist[-1]['kl']:.2f}  ({time.time() - t0:.0f}s)")
    return model.cpu(), hist


@torch.no_grad()
def manifold(model: ConvVAE, n: int = 15, span: float = 2.5) -> torch.Tensor:
    """Decode a regular grid over the 2-d latent plane (positions chosen as Gaussian quantiles) into an n x n picture of digits."""
    q = torch.distributions.Normal(0, 1).icdf(torch.linspace(0.5 / n, 1 - 0.5 / n, n)).clamp(-span, span)
    zs = torch.stack(torch.meshgrid(q, q.flip(0), indexing="xy"), -1).view(-1, 2)
    return torch.sigmoid(model.eval().decode(zs))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--epochs", type=int, default=12)
    ap.add_argument("--smoke", action="store_true")
    a = ap.parse_args()
    epochs, limit = (1, 2000) if a.smoke else (a.epochs, None)
    runs = {"z2_beta1": (2, 1.0), "z16_beta1": (16, 1.0), "z16_beta0.1": (16, 0.1), "z16_beta4": (16, 4.0)}
    models, hists = {}, {}
    for name, (z, beta) in runs.items():
        models[name], hists[name] = train(z, epochs, beta, limit=limit)
        torch.save(models[name].state_dict(), run_dir("vae") / f"vae_{name}.pt")
    results = {"epochs": epochs, "runs": {n: {"latent": runs[n][0], "beta": runs[n][1], **hists[n][-1]} for n in runs},
               "history_z16_beta1": hists["z16_beta1"]}
    save_results("vae", results)
    if a.smoke:
        print(results["runs"])
        return

    import matplotlib.pyplot as plt

    style()
    xt, yt = load_mnist(False)
    fig = plt.figure(figsize=(15, 9))
    gs = fig.add_gridspec(2, 3, height_ratios=[1.15, 1])
    ax = fig.add_subplot(gs[0, 0])
    image_grid(manifold(models["z2_beta1"]), 15, ax, "Learned 2-d manifold: decoded grid of the latent plane")
    ax = fig.add_subplot(gs[0, 1])
    with torch.no_grad():
        mu = models["z2_beta1"].eval().encode(xt[:4000])[0].numpy()
    sc = ax.scatter(mu[:, 0], mu[:, 1], c=yt[:4000].numpy(), cmap="tab10", s=5)
    ax.set(title="Encoded test digits (posterior means)", xlabel="z1", ylabel="z2")
    fig.colorbar(sc, ax=ax, ticks=range(10), shrink=.8)
    ax = fig.add_subplot(gs[0, 2])
    names = list(runs)
    ax.bar(range(len(names)), [results["runs"][n]["recon"] for n in names], label="reconstruction")
    ax.bar(range(len(names)), [results["runs"][n]["kl"] for n in names], bottom=[results["runs"][n]["recon"] for n in names], label="KL")
    ax.set_xticks(range(len(names)), [n.replace("_", "\n") for n in names], fontsize=8)
    ax.set(ylabel="nats per image (held-out)", title="Negative ELBO = reconstruction + KL")
    ax.legend()
    m16 = models["z16_beta1"].eval()
    with torch.no_grad():
        samples = torch.sigmoid(m16.decode(torch.randn(64, 16, generator=torch.Generator().manual_seed(2))))
        recon = torch.sigmoid(m16(xt[:16])[0])
    ax = fig.add_subplot(gs[1, 0])
    image_grid(samples, 16, ax, "64 digits sampled from N(0, I) through the decoder (z=16)")
    ax = fig.add_subplot(gs[1, 1:])
    image_grid(torch.cat([xt[:16], recon]), 16, ax, "Held-out digits (top) and their VAE reconstructions (bottom)")
    fig.tight_layout()
    save_figure(fig, "vae")
    print({n: {k: round(v, 3) for k, v in r.items()} for n, r in results["runs"].items()})


if __name__ == "__main__":
    main()
