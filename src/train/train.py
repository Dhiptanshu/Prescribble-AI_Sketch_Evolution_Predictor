"""Train one model variant and evaluate accuracy-vs-completion.

python -m src.train.train --model fusion_ghost --epochs 12
Outputs runs/<model>/{best.pt, log.csv, results.json}
"""
import argparse
import csv
import json
import time

import torch
import torch.nn.functional as F
from torch.utils.data import DataLoader

from src.common import EVAL_FRACS, SET_RUNS
from src.data.dataset import PartialSketchTrain, as_float, eval_set, load_splits
from src.models.nets import VARIANTS, build


@torch.no_grad()
def evaluate(model, data, bs=512, dev="cpu"):
    """Top-1/Top-5 (and mean ghost BCE) per completion fraction."""
    model.eval()
    res = {}
    for frac, d in data.items():
        n, c1, c5, rl = len(d["y"]), 0, 0, 0.0
        for i in range(0, n, bs):
            sl = slice(i, i + bs)
            b = {k: v.to(dev) for k, v in as_float({k: v[sl] for k, v in d.items()}).items()}
            logits, recon = model(b["img"], b["seq"], b["len"])
            top5 = logits.topk(5, dim=1).indices
            y = b["y"]
            c1 += (top5[:, 0] == y).sum().item()
            c5 += (top5 == y[:, None]).any(1).sum().item()
            if recon is not None:
                rl += F.binary_cross_entropy_with_logits(recon, b["target"], reduction="sum").item()
        res[frac] = {"top1": c1 / n, "top5": c5 / n, "ghost_bce": rl / n / 4096 if rl else None}
    return res


def mean_top1(res):
    return sum(v["top1"] for v in res.values()) / len(res)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", choices=list(VARIANTS), required=True)
    ap.add_argument("--epochs", type=int, default=12)
    ap.add_argument("--epoch-size", type=int, default=50000)
    ap.add_argument("--bs", type=int, default=128)
    ap.add_argument("--lr", type=float, default=2e-3)
    ap.add_argument("--workers", type=int, default=6)
    ap.add_argument("--threads", type=int, default=8)
    ap.add_argument("--ghost-weight", type=float, default=1.0)
    ap.add_argument("--smoke", action="store_true", help="tiny run to check the pipeline")
    a = ap.parse_args()

    torch.set_num_threads(a.threads)
    torch.manual_seed(0)
    out = SET_RUNS / a.model
    out.mkdir(parents=True, exist_ok=True)

    splits = load_splits()
    sk, lb = splits["train"]
    if a.smoke:
        a.epochs, a.epoch_size = 1, 2048
    train_dl = DataLoader(PartialSketchTrain(sk, lb, a.epoch_size), batch_size=a.bs, shuffle=False,
                          num_workers=a.workers, drop_last=True, persistent_workers=a.workers > 0)
    val = eval_set("val")
    if a.smoke:
        val = {f: {k: v[:512] for k, v in d.items()} for f, d in val.items()}

    dev = "cuda" if torch.cuda.is_available() else "cpu"
    model = build(a.model).to(dev)
    print("device:", dev, flush=True)
    print(f"{a.model}: {sum(p.numel() for p in model.parameters()) / 1e6:.2f}M params", flush=True)
    opt = torch.optim.AdamW(model.parameters(), lr=a.lr, weight_decay=1e-4)
    sched = torch.optim.lr_scheduler.OneCycleLR(opt, max_lr=a.lr, total_steps=a.epochs * len(train_dl))
    pos_w = torch.tensor(4.0, device=dev)

    best, rows = -1.0, []
    for ep in range(1, a.epochs + 1):
        model.train()
        t0, tot, n = time.time(), 0.0, 0
        for b in train_dl:
            b = {k: v.to(dev, non_blocking=True) for k, v in b.items()}
            logits, recon = model(b["img"], b["seq"], b["len"])
            loss = F.cross_entropy(logits, b["y"], label_smoothing=0.05)
            if recon is not None:
                loss = loss + a.ghost_weight * F.binary_cross_entropy_with_logits(recon, b["target"], pos_weight=pos_w)
            opt.zero_grad(set_to_none=True)
            loss.backward()
            opt.step()
            sched.step()
            tot, n = tot + loss.item(), n + 1
        res = evaluate(model, val, dev=dev)
        score = mean_top1(res)
        row = {"epoch": ep, "loss": tot / n, "val_mean_top1": score, "secs": time.time() - t0,
               **{f"top1@{int(f * 100)}": v["top1"] for f, v in res.items()}}
        rows.append(row)
        print(" ".join(f"{k}={v:.3f}" if isinstance(v, float) else f"{k}={v}" for k, v in row.items()), flush=True)
        if score > best:
            best = score
            torch.save(model.state_dict(), out / "best.pt")
        with open(out / "log.csv", "w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=rows[0].keys())
            w.writeheader()
            w.writerows(rows)

    model.load_state_dict(torch.load(out / "best.pt", map_location=dev))
    test = evaluate(model, eval_set("test"), dev=dev)
    with open(out / "results.json", "w") as f:
        json.dump({str(k): v for k, v in test.items()}, f, indent=2)
    print("TEST", {k: round(v["top5"], 3) for k, v in test.items()}, "(top5)", flush=True)


if __name__ == "__main__":
    main()
