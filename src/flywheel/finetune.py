"""Adapt a trained model to real users' drawings and measure what that bought, on drawings the training never saw.

    python -m src.flywheel.finetune --base runs/v2/fusion_ghost/best.pt --user-file training.jsonl [--input-type mouse] [--epochs 6]

1. Score the BASE model on the held-out fifth of the user drawings and on QuickDraw's test set.
2. Fine-tune it (low learning rate, QuickDraw replay mixed with the user training drawings, src/train/train.py).
3. Score the fine-tuned model on exactly the same two sets and write the before / after table to results.json.
Gain on the user drawings is the point; the QuickDraw column shows whether anything was forgotten along the way.
Needs the data of the current class set (PRESCRIBBLE_CLASS_SET), and enough user drawings to judge by (see MIN_HELDOUT).
"""
import argparse
import json
import subprocess
import sys
from pathlib import Path

import torch

from src.common import EVAL_FRACS, SET_RUNS
from src.data.dataset import build_eval_tensors, eval_set
from src.flywheel.mix import user_arrays
from src.models.nets import build
from src.train.train import evaluate

MIN_HELDOUT = 30         # fewer held-out real drawings than this cannot support a conclusion


def score(model, user_sketches, user_labels, dev) -> dict:
    """Top-1 / Top-5 per completion fraction on the user drawings and on QuickDraw's test set."""
    user = {f: build_eval_tensors(user_sketches, user_labels, f) for f in EVAL_FRACS}
    return {"user": evaluate(model, user, dev=dev), "quickdraw": evaluate(model, eval_set("test"), dev=dev)}


def load(path: Path, dev, architecture: str = "fusion_ghost"):
    model = build(architecture).to(dev)
    model.load_state_dict(torch.load(path, map_location=dev))
    return model.eval()


def user_share(cap: float, max_repeats: float, n_user: int, total_samples: int) -> float:
    """Fraction of the training stream that is user drawings: the requested share, but never so much that each user drawing is looked at
    more than `max_repeats` times (a few hundred drawings seen dozens of times each would simply be memorised). Always at least 1%."""
    return min(cap, max(0.01, max_repeats * n_user / max(1, total_samples)))


def table(before: dict, after: dict) -> str:
    rows = ["| Set | Metric | " + " | ".join(f"{int(f * 100)}%" for f in EVAL_FRACS) + " |", "|---|---|" + "---:|" * len(EVAL_FRACS)]
    for name in ("user", "quickdraw"):
        for metric in ("top1", "top5"):
            for tag, res in (("before", before), ("after", after)):
                rows.append(f"| {name} ({tag}) | {metric} | " + " | ".join(f"{res[name][f][metric] * 100:.1f}" for f in EVAL_FRACS) + " |")
    return "\n".join(rows)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", type=Path, required=True)
    ap.add_argument("--user-file", type=Path, required=True)
    ap.add_argument("--input-type", help="restrict to drawings made with this pointer (mouse, touch, pen)")
    ap.add_argument("--epochs", type=int, default=6)
    ap.add_argument("--epoch-size", type=int, default=60000)
    ap.add_argument("--lr", type=float, default=4e-4)
    ap.add_argument("--user-share", type=float, default=0.25, help="at most this fraction of the training stream is user drawings")
    ap.add_argument("--max-repeats", type=float, default=10, help="and no user drawing is seen more than about this many times (stops a few drawings being memorised)")
    ap.add_argument("--model", default="fusion_ghost", help="architecture of the base checkpoint (see src/models/nets.py VARIANTS)")
    ap.add_argument("--name", default="fusion_ghost_ft")
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--min-heldout", type=int, default=MIN_HELDOUT, help="refuse to judge on fewer held-out real drawings than this")
    ap.add_argument("--smoke", action="store_true", help="tiny run to check the pipeline (the numbers mean nothing)")
    a = ap.parse_args()

    dev = "cuda" if torch.cuda.is_available() else "cpu"
    train_sk, _, held_sk, held_lb = user_arrays(a.user_file, a.input_type)
    if len(held_sk) < a.min_heldout:
        sys.exit(f"only {len(held_sk)} held-out real drawings (need {a.min_heldout}): collect more before judging an adaptation")
    share = user_share(a.user_share, a.max_repeats, len(train_sk), a.epochs * a.epoch_size)
    print(f"{len(train_sk)} user drawings train; they make up {share:.1%} of the stream (cap {a.user_share:.0%}, at most ~{a.max_repeats:g} looks each)", flush=True)
    before = score(load(a.base, dev, a.model), held_sk, held_lb, dev)
    print(f"base scored on {len(held_sk)} held-out real drawings", flush=True)

    cmd = [sys.executable, "-m", "src.train.train", "--model", a.model, "--init", str(a.base), "--user-file", str(a.user_file),
           "--user-share", f"{share:.6f}", "--epochs", str(a.epochs), "--epoch-size", str(a.epoch_size), "--lr", str(a.lr), "--bs", "256",
           "--workers", str(a.workers), "--out-name", a.name]
    if a.smoke:
        cmd.append("--smoke")
    if a.input_type:
        cmd += ["--user-input-type", a.input_type]
    if subprocess.run(cmd).returncode != 0:
        sys.exit("fine-tuning failed")

    after = score(load(SET_RUNS / a.name / "best.pt", dev, a.model), held_sk, held_lb, dev)
    result = {"heldout_user_drawings": len(held_sk), "input_type": a.input_type, "epochs": a.epochs, "user_share": share, "user_training_drawings": len(train_sk), "lr": a.lr,
              "before": {k: {str(f): v for f, v in r.items()} for k, r in before.items()},
              "after": {k: {str(f): v for f, v in r.items()} for k, r in after.items()}}
    (SET_RUNS / a.name / "adaptation.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(table(before, after))


if __name__ == "__main__":
    main()
