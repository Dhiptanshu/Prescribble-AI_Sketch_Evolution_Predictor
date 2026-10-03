"""Module II: a convolutional autoencoder on MNIST.

Three studies: (1) how the bottleneck size limits reconstruction, (2) what a 2-number code looks like, (3) denoising.
python -m src.syllabus.ae [--epochs 10] [--smoke]
Outputs runs/syllabus/ae/{results.json, ae_z*.pt} and report/figures/syllabus_ae.png
"""
import argparse
import time

import torch
import torch.nn as nn
import torch.nn.functional as F

from src.syllabus.common import device, image_grid, load_mnist, run_dir, save_figure, save_results, seed_all, style


class ConvAE(nn.Module):
    """28x28 -> 14 -> 7 -> latent vector -> 7 -> 14 -> 28. The decoder returns logits (the loss is binary cross-entropy)."""

    def __init__(self, latent: int):
        super().__init__()
        self.latent = latent
        self.enc = nn.Sequential(nn.Conv2d(1, 16, 3, 2, 1), nn.ReLU(inplace=True), nn.Conv2d(16, 32, 3, 2, 1), nn.ReLU(inplace=True),
                                 nn.Flatten(), nn.Linear(32 * 49, latent))
        self.dec_fc = nn.Sequential(nn.Linear(latent, 32 * 49), nn.ReLU(inplace=True))
        self.dec = nn.Sequential(nn.ConvTranspose2d(32, 16, 3, 2, 1, output_padding=1), nn.ReLU(inplace=True),
                                 nn.ConvTranspose2d(16, 1, 3, 2, 1, output_padding=1))

    def encode(self, x):
        return self.enc(x)

    def decode(self, z):
        return self.dec(self.dec_fc(z).view(-1, 32, 7, 7))

    def forward(self, x):
        z = self.encode(x)
        return self.decode(z), z


def train(latent: int, epochs: int, denoise: float = 0.0, bs: int = 128, limit: int | None = None, log=print):
    """Returns the trained model (on CPU) and its per-epoch test loss. `denoise` = std of Gaussian noise added to the INPUT only."""
    dev = device()
    seed_all(latent)
    x, _ = load_mnist(True, limit)
    xt, _ = load_mnist(False, limit)
    x, xt = x.to(dev), xt.to(dev)
    model = ConvAE(latent).to(dev)
    opt = torch.optim.Adam(model.parameters(), lr=2e-3)
    hist = []
    for ep in range(1, epochs + 1):
        model.train()
        perm, t0 = torch.randperm(len(x), device=dev), time.time()
        for i in range(0, len(x), bs):
            clean = x[perm[i:i + bs]]
            noisy = (clean + denoise * torch.randn_like(clean)).clamp(0, 1) if denoise else clean
            loss = F.binary_cross_entropy_with_logits(model(noisy)[0], clean)
            opt.zero_grad(set_to_none=True)
            loss.backward()
            opt.step()
        hist.append(evaluate(model, xt, denoise))
        log(f"z={latent:3d} denoise={denoise}  epoch {ep:2d}  test mse {hist[-1]['mse']:.5f}  ({time.time() - t0:.0f}s)")
    return model.cpu(), hist


@torch.no_grad()
def evaluate(model: ConvAE, xt: torch.Tensor, denoise: float = 0.0) -> dict:
    model.eval()
    dev = next(model.parameters()).device
    g = torch.Generator(device="cpu").manual_seed(123)
    mse = bce = 0.0
    for i in range(0, len(xt), 1000):
        clean = xt[i:i + 1000].to(dev)
        noisy = (clean + denoise * torch.randn(clean.shape, generator=g).to(dev)).clamp(0, 1) if denoise else clean
        logits = model(noisy)[0]
        mse += F.mse_loss(torch.sigmoid(logits), clean, reduction="sum").item()
        bce += F.binary_cross_entropy_with_logits(logits, clean, reduction="sum").item()
    n = len(xt) * 784
    return {"mse": mse / n, "bce": bce / n}


@torch.no_grad()
def reconstruct(model: ConvAE, x: torch.Tensor) -> torch.Tensor:
    model.eval()
    return torch.sigmoid(model(x)[0])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--epochs", type=int, default=10)
    ap.add_argument("--smoke", action="store_true")
    a = ap.parse_args()
    epochs, limit = (1, 2000) if a.smoke else (a.epochs, None)
    latents = [2, 8, 32]
    models, curves = {}, {}
    for z in latents:
        models[z], hist = train(z, epochs, limit=limit)
        curves[z] = hist
        torch.save(models[z].state_dict(), run_dir("ae") / f"ae_z{z}.pt")
    den_model, den_hist = train(32, epochs, denoise=0.5, limit=limit)
    plain_on_noisy = evaluate(models[32], load_mnist(False, limit)[0].to(device()), denoise=0.5)

    xt, yt = load_mnist(False, limit)
    results = {
        "epochs": epochs,
        "bottleneck": {str(z): {"test_mse": curves[z][-1]["mse"], "test_bce": curves[z][-1]["bce"], "compression": round(784 / z, 1)} for z in latents},
        "denoising": {"noise_std": 0.5, "denoising_ae_mse_on_noisy_input": den_hist[-1]["mse"], "plain_ae_mse_on_noisy_input": plain_on_noisy["mse"],
                      "mse_of_the_noisy_image_itself": float(torch.mean(((xt + 0.5 * torch.randn(xt.shape, generator=torch.Generator().manual_seed(123))).clamp(0, 1) - xt) ** 2))},
    }
    save_results("ae", results)
    if a.smoke:
        print(results)
        return

    import matplotlib.pyplot as plt

    style()
    fig = plt.figure(figsize=(15, 8.4))
    gs = fig.add_gridspec(3, 3, height_ratios=[1, 1, 1.25])
    sample = xt[:16]
    rows = [("original", sample)] + [(f"z = {z}", reconstruct(models[z], sample)) for z in latents]
    ax = fig.add_subplot(gs[0:2, 0:2])
    image_grid(torch.cat([r[1] for r in rows]), 16, ax, "Reconstructions of held-out digits:  original / z=2 / z=8 / z=32")
    ax = fig.add_subplot(gs[0, 2])
    ax.plot(latents, [curves[z][-1]["mse"] for z in latents], marker="o")
    ax.set(xscale="log", xticks=latents, xticklabels=latents, xlabel="bottleneck size z", ylabel="test MSE", title="Bottleneck vs reconstruction error")
    ax = fig.add_subplot(gs[1, 2])
    with torch.no_grad():
        codes = models[2].eval().encode(xt[:4000]).numpy()
    sc = ax.scatter(codes[:, 0], codes[:, 1], c=yt[:4000].numpy(), cmap="tab10", s=5)
    ax.set(title="The 2-number code of 4000 test digits", xlabel="z1", ylabel="z2")
    fig.colorbar(sc, ax=ax, ticks=range(10), shrink=.8)
    clean = xt[:12]
    noisy = (clean + 0.5 * torch.randn(clean.shape, generator=torch.Generator().manual_seed(1))).clamp(0, 1)
    ax = fig.add_subplot(gs[2, :])
    image_grid(torch.cat([clean, noisy, reconstruct(models[32], noisy), reconstruct(den_model, noisy)]), 12, ax,
               "Denoising (noise std 0.5):  clean / noisy input / plain AE output / denoising AE output")
    fig.tight_layout()
    save_figure(fig, "ae")
    print(results)


if __name__ == "__main__":
    main()
