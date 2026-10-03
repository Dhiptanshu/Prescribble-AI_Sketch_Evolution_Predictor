"""Module V: VGG16 transfer learning on the partial sketches, in a controlled comparison.

All models see ONLY the 64x64 raster (no stroke sequence, no ghost head), the same training stream and the same evaluation, so the
differences come from the network and from how much of it is trained:
  vgg16_frozen    ImageNet VGG16 features frozen, only a new classifier trained (classic feature extraction)
  vgg16_finetune  the same network with every layer trained at a low learning rate
  resnet18_finetune  ImageNet ResNet18, fully fine-tuned (the family used in Module V of the main model)
  cnn (existing)  the small from-scratch CNN, from runs/cnn/results.json (trained on the identical stream)

python -m src.syllabus.vgg_transfer [--epochs 8] [--epoch-size 60000] [--smoke]
Outputs runs/syllabus/vgg/results.json and report/figures/syllabus_vgg.png
"""
import argparse
import json
import time

import torch
import torch.nn as nn
import torch.nn.functional as F
from torch.utils.data import DataLoader

from src.common import EVAL_FRACS, NUM_CLASSES, RUNS_DIR
from src.data.dataset import PartialSketchTrain, as_float, eval_set, load_splits
from src.syllabus.common import device, run_dir, save_figure, save_results, seed_all, style

MEAN, STD = 0.449, 0.226                       # ImageNet luminance statistics, applied to the replicated channel


class ImageNetBackbone(nn.Module):
    """Wraps a torchvision VGG16 or ResNet18: 1-channel 64x64 raster -> class logits."""

    def __init__(self, arch: str, freeze: bool, pretrained: bool = True):
        super().__init__()
        import torchvision

        if arch == "vgg16":
            w = torchvision.models.VGG16_Weights.IMAGENET1K_V1 if pretrained else None
            self.features = torchvision.models.vgg16(weights=w).features              # 64x64 -> 2x2x512
            feat = 512 * 2 * 2
        else:
            w = torchvision.models.ResNet18_Weights.IMAGENET1K_V1 if pretrained else None
            net = torchvision.models.resnet18(weights=w)
            net.fc = nn.Identity()
            self.features = net
            feat = 512
        self.frozen = freeze
        if freeze:
            for p in self.features.parameters():
                p.requires_grad = False
        self.head = nn.Sequential(nn.Flatten(), nn.Linear(feat, 256), nn.ReLU(inplace=True), nn.Dropout(0.4), nn.Linear(256, NUM_CLASSES))

    def forward(self, img):
        x = ((img - MEAN) / STD).expand(-1, 3, -1, -1)
        if self.frozen:
            self.features.eval()                 # keep BatchNorm statistics fixed too
            with torch.no_grad():
                f = self.features(x)
        else:
            f = self.features(x)
        return self.head(f)


@torch.no_grad()
def evaluate(model: nn.Module, data: dict, dev, bs: int = 500) -> dict:
    model.eval()
    res = {}
    for frac, d in data.items():
        n, c1, c5 = len(d["y"]), 0, 0
        for i in range(0, n, bs):
            img = d["img"][i:i + bs].to(dev).float() / 255
            y = d["y"][i:i + bs].to(dev)
            top5 = model(img).topk(5, dim=1).indices
            c1 += (top5[:, 0] == y).sum().item()
            c5 += (top5 == y[:, None]).any(1).sum().item()
        res[str(frac)] = {"top1": c1 / n, "top5": c5 / n}
    return res


def train_one(name: str, arch: str, freeze: bool, lr: float, epochs: int, epoch_size: int, test, bs: int = 128, workers: int = 4, log=print) -> dict:
    dev = device()
    seed_all(0)
    sk, lb = load_splits()["train"]
    loader = DataLoader(PartialSketchTrain(sk, lb, epoch_size), batch_size=bs, num_workers=workers, shuffle=False, drop_last=True,
                        persistent_workers=workers > 0)
    model = ImageNetBackbone(arch, freeze).to(dev)
    params = [p for p in model.parameters() if p.requires_grad]
    opt = torch.optim.AdamW(params, lr=lr, weight_decay=1e-4)
    sched = torch.optim.lr_scheduler.OneCycleLR(opt, max_lr=lr, total_steps=epochs * len(loader))
    hist = []
    for ep in range(1, epochs + 1):
        model.train()
        t0, tot, n = time.time(), 0.0, 0
        for b in loader:
            logits = model(b["img"].to(dev))
            loss = F.cross_entropy(logits, b["y"].to(dev), label_smoothing=0.05)
            opt.zero_grad(set_to_none=True)
            loss.backward()
            opt.step()
            sched.step()
            tot, n = tot + loss.item() * len(b["y"]), n + len(b["y"])
        m = evaluate(model, {0.3: test[0.3]}, dev)["0.3"]
        hist.append({"epoch": ep, "loss": tot / n, "top5_at_30": m["top5"]})
        log(f"{name}  epoch {ep}  loss {tot / n:.3f}  Top-5 @30% {m['top5']:.3f}  ({time.time() - t0:.0f}s)")
    return {"name": name, "arch": arch, "frozen_backbone": freeze, "lr": lr, "epochs": epochs, "trainable_params": sum(p.numel() for p in params),
            "total_params": sum(p.numel() for p in model.parameters()), "by_fraction": evaluate(model, test, dev), "history": hist}


def figure(results: list[dict], baseline: dict | None):
    import matplotlib.pyplot as plt

    style()
    fig, axs = plt.subplots(1, 2, figsize=(13, 4.4))
    for r in results:
        xs = sorted(r["by_fraction"], key=float)
        for ax, key in zip(axs, ("top5", "top1")):
            ax.plot([float(x) * 100 for x in xs], [r["by_fraction"][x][key] * 100 for x in xs], marker="o", label=r["name"])
    if baseline:
        xs = sorted(baseline, key=float)
        for ax, key in zip(axs, ("top5", "top1")):
            ax.plot([float(x) * 100 for x in xs], [baseline[x][key] * 100 for x in xs], marker="s", ls="--", color="k", label="small CNN from scratch")
    for ax, key in zip(axs, ("Top-5", "Top-1")):
        ax.set(xlabel="% of the sketch drawn", ylabel=f"{key} accuracy (%)", title=f"{key} accuracy vs completion (image only)")
        ax.legend(fontsize=8)
    fig.tight_layout()
    return fig


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--epochs", type=int, default=8)
    ap.add_argument("--epoch-size", type=int, default=60000)
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--smoke", action="store_true")
    a = ap.parse_args()
    epochs, size, workers = (1, 512, 0) if a.smoke else (a.epochs, a.epoch_size, a.workers)
    test = eval_set("test")
    if a.smoke:                                          # a tiny slice: the point is to prove the pipeline runs, not to measure
        test = {f: {k: v[:200] for k, v in d.items()} for f, d in test.items()}
    plan = [("vgg16_frozen", "vgg16", True, 2e-3), ("vgg16_finetune", "vgg16", False, 2e-4), ("resnet18_finetune", "resnet18", False, 1e-3)]
    results = [train_one(n, arch, fr, lr, epochs, size, test, workers=workers) for n, arch, fr, lr in plan]
    base_file = RUNS_DIR / "cnn" / "results.json"
    baseline = json.loads(base_file.read_text()) if base_file.exists() else None
    save_results("vgg", {"models": results, "small_cnn_from_scratch": baseline})
    if not a.smoke:
        save_figure(figure(results, baseline), "vgg")
    for r in results:
        print(r["name"], {f: round(v["top5"], 3) for f, v in r["by_fraction"].items()})


if __name__ == "__main__":
    main()
