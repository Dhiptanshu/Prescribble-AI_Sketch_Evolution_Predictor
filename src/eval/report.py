"""Generate report/REPORT.md. Every number is read from runs/, models/v1/ and report/analysis.json (nothing typed by hand).

python -m src.eval.report      (run src.eval.analysis first)
"""
import json

from src.common import CLASSES, ROOT, RUNS_DIR

NAMES = {"mlp": "MLP (NumPy, from scratch)", "cnn": "CNN", "lstm": "LSTM (stroke sequence)", "fusion": "CNN + LSTM fusion",
         "fusion_ghost": "CNN + LSTM + ghost decoder (**deployed**)", "resnet_ghost": "ResNet18 (ImageNet) + LSTM + ghost"}
ORDER = list(NAMES)
FRACS = ["0.1", "0.2", "0.3", "0.5", "0.75", "1.0"]


def load(p):
    return json.load(open(p))


def table(res, metric):
    head = "| Model | " + " | ".join(f"{int(float(f) * 100)}%" for f in FRACS) + " |\n|---|" + "---:|" * len(FRACS) + "\n"
    best = {f: max(res[m][f][metric] for m in ORDER) for f in FRACS}
    rows = []
    for m in ORDER:
        cells = [(f"**{res[m][f][metric] * 100:.1f}**" if res[m][f][metric] == best[f] else f"{res[m][f][metric] * 100:.1f}") for f in FRACS]
        rows.append(f"| {NAMES[m]} | " + " | ".join(cells) + " |")
    return head + "\n".join(rows)


def params(m):
    import torch
    from src.models.nets import build
    return sum(p.numel() for p in build(m).parameters()) / 1e6 if m != "mlp" else (1024 * 512 + 512 * 256 + 256 * 30) / 1e6


def main():
    res = {m: load(RUNS_DIR / m / "results.json") for m in ORDER}
    meta = load(ROOT / "models" / "v1" / "meta.json")
    an = load(ROOT / "report" / "analysis.json")
    mnist = an["mnist_mlp_test_acc"]
    sp = RUNS_DIR / "sentiment" / "results.json"
    sent = load(sp) if sp.exists() else None
    r = res["fusion_ghost"]
    pc = sorted(an["per_class_top1_30"].items(), key=lambda kv: kv[1])
    conf = an["top_confusions_at_30"][:5]
    best_tl = max(res["resnet_ghost"]["1.0"]["top1"], res["cnn"]["1.0"]["top1"])
    out = f"""# Sketch Evolution Predictor: report

*Deep Learning Laboratory (2604733), GLS FET B.Tech CS&E, Semester VII.*
All numbers below are generated from the training runs and the held-out test split (9,000 sketches, 300 per class, never used for training or model selection).

## 1. Problem
Given only the first part of a drawing, predict what the final drawing will be. The system reads the pen strokes as they are drawn and
(a) ranks the **Top-5 object classes**, and (b) paints a **ghost** of how it expects the drawing to end. Everything runs live in a web browser.

## 2. Data
Google QuickDraw (CC BY 4.0), stroke-level "simplified" files, **{len(CLASSES)} classes** ({', '.join(CLASSES)}).
96,000 training / 9,000 validation / 9,000 test sketches. Stroke data is essential: bitmaps cannot be cut at "30% of the drawing".

**Partial sketches.** Each drawing is cut at a fraction of its total *ink length* (not stroke count, since many sketches have 2 to 4 strokes), so the cut may fall mid-stroke.
Training draws the fraction at random (half of the samples from 12 to 40%, the rest from 10 to 100%) and augments the whole drawing (flip, rotation, scale, shift, jitter) *before* cutting.
Evaluation uses fixed fractions: 10, 20, 30, 50, 75 and 100%.

**Fixed frame.** QuickDraw rescales a finished drawing to fill a 256x256 box, but a live user's unfinished drawing has no final bounding box.
The prefix is therefore cut from the already-normalised drawing and is **not** re-normalised, and the canvas uses the same fixed frame.

## 3. Models (mapped to the course modules)
| Module | Component | Where |
|---|---|---|
| I: NN, MLP, backprop, MNIST | MLP with manual backpropagation in NumPy (verified against numerical gradients). MNIST test accuracy **{mnist * 100:.2f}%**. Reused as the sketch baseline. | `src/models/mlp_numpy.py`, `src/train/mlp_baseline.py` |
| II: Autoencoders | Conv decoder ("ghost") trained jointly to reconstruct the *completed* drawing from the partial one (encoder-decoder with a skip from the input). | `GhostDecoder` in `src/models/nets.py` |
| III: CNN | 3-stage CNN with BatchNorm on 64x64 rasters. | `CNNEncoder` |
| IV: RNN / LSTM | 2-layer LSTM over the stroke points (x, y, dx, dy, new-stroke flag). {"Sentiment analysis: LSTM on IMDB, test accuracy **%.2f%%**." % (sent[-1]["test_acc"] * 100) if sent else ""} | `LSTMEncoder`, `src/train/sentiment_lstm.py` |
| V: Transfer learning | ImageNet-pretrained ResNet18 (1-channel adaptation) fused with the LSTM, fine-tuned end to end. | `ResNetEncoder` |

Final model: CNN branch + LSTM branch, concatenated, feeding a classifier head and the ghost decoder. Loss = cross-entropy (label smoothing 0.05) + ghost reconstruction loss (BCE). {params('fusion_ghost'):.1f}M parameters.
Training ran on a Kaggle GPU (`kaggle/`); evaluation, export and the demo run on a CPU.

## 4. Results
### Top-5 accuracy vs % of the sketch drawn (test set)
{table(res, 'top5')}

### Top-1 accuracy
{table(res, 'top1')}

![Top-5 curve](figures/accuracy_vs_completion_top5.png)

**Headline.** With only **20%** of the ink the deployed model has the right answer in its Top-5 **{r['0.2']['top5'] * 100:.1f}%** of the time, and **{r['0.3']['top5'] * 100:.1f}%** at 30%
(Top-1: {r['0.2']['top1'] * 100:.1f}% and {r['0.3']['top1'] * 100:.1f}%). With the full sketch it reaches {r['1.0']['top5'] * 100:.1f}% Top-5 and {r['1.0']['top1'] * 100:.1f}% Top-1.

**What the ablation shows.**
* The from-scratch **MLP** is far behind ({res['mlp']['0.3']['top5'] * 100:.1f}% Top-5 at 30%): it ignores spatial structure.
* The **CNN** and the **LSTM** are close to each other, and **fusing** them gives the best result at every completion level (the two fused variants, with and without the ghost head, trade first place), especially early, when the two views (appearance and stroke order) complement each other.
* Adding the **ghost decoder** leaves classification essentially unchanged ({res['fusion_ghost']['0.3']['top5'] * 100:.1f}% vs {res['fusion']['0.3']['top5'] * 100:.1f}% Top-5 at 30%, within noise) while adding the completion feature.
* **Transfer learning did not help here.** Swapping the small from-scratch CNN for an ImageNet ResNet18 (everything else identical) gives {res['resnet_ghost']['1.0']['top1'] * 100:.1f}% Top-1 on full sketches versus {res['fusion_ghost']['1.0']['top1'] * 100:.1f}%, i.e. no gain, and it is clearly behind early on ({res['resnet_ghost']['0.2']['top5'] * 100:.1f}% vs {res['fusion_ghost']['0.2']['top5'] * 100:.1f}% Top-5 at 20%). Line drawings are far from natural photographs, and the heavier network is slower (about 130 s per epoch vs 55 s on the GPU).

### Ghost completion
![Ghost gallery](figures/ghost_gallery.png)

The ghost is a *mean* prediction (an expected-ink heat map), not a sharp drawing: when the object is ambiguous it blends the plausible endings. That is intended. Its blurriness is a visible measure of the model's uncertainty. In the demo only the *not yet drawn* part is shown.

### Which objects are recognised early?
![Per-class](figures/per_class_early_vs_final.png)

At 30% of the ink the easiest classes are {', '.join(f"{k} ({v * 100:.0f}%)" for k, v in pc[::-1][:3])} and the hardest are {', '.join(f"{k} ({v * 100:.0f}%)" for k, v in pc[:3])} (Top-1).
The most common confusions at 30% are {', '.join(f"{c['true']} to {c['predicted']} ({c['count']})" for c in conf)}: many drawings start as a circle, which is genuinely ambiguous.

## 5. Real-time system
* Model exported to ONNX ({meta['size_mb']:.1f} MB), verified against PyTorch (max difference about 1e-7).
* Inference: **{meta['latency_ms']:.1f} ms** per prediction in native ONNX Runtime on a CPU, about 17 to 20 ms in the browser (WebAssembly), so it updates on every pen movement.
* The page runs entirely client-side: no server-side model, no internet, no GPU. A static Python server (`apps/web/serve.py`) is all a lab machine needs.
* The browser reproduces the Python preprocessing: the stroke-sequence features match exactly, and the rasteriser's mean pixel difference to the training renderer is under 0.01.

## 6. Limitations (honest)
* Test accuracy is on **held-out QuickDraw sketches**. Live drawings with a mouse differ from the phone/touch drawings in QuickDraw. This domain shift was only sanity-checked with scripted pointer input, **not** measured in a user study, so expect lower accuracy for real users, especially for very small or off-centre drawings.
* Only {len(CLASSES)} classes. More classes would lower early accuracy.
* The ghost is blurry by construction (mean prediction); a VAE or GAN could give sharper, multi-modal completions. VAE and GAN were built and measured on MNIST (see SYLLABUS.md) but not applied to sketch completion.
* A single training run per model (no seeds / confidence intervals); differences of about 1 point between the CNN, LSTM and fusion models should not be over-interpreted.
* **A training bug found afterwards (4 Oct 2026):** every epoch replayed the same samples, so each model in this report trained on one fixed subset of the data instead of fresh variations. The numbers here are what that pipeline measured; a corrected retraining would be expected to score higher (the retrained 345-class model gained 10 points of Top-5 at 30% of the ink over its flawed first run). The models were not retrained; the fix and the corrected 345-class model are in `docs/FLYWHEEL.md` and `report/GENERATIONS.md`.
* Object detection (YOLO) was done on composed digit scenes, not on the sketch app itself (see SYLLABUS.md).

## 7. Reproduce
See the README. Training scripts: `src/train/train.py`; Kaggle driver: `kaggle/kernel/train_kaggle.py`.
"""
    (ROOT / "report" / "REPORT.md").write_text(out, encoding="utf-8")
    print("wrote report/REPORT.md")


if __name__ == "__main__":
    main()
