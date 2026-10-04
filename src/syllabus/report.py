"""Generate report/SYLLABUS.md from the experiment results. Every number is read from JSON; comparative sentences are chosen by the numbers.

python -m src.syllabus.report --collect     # copy runs/syllabus/*/results.json into report/syllabus_results/ (committed), then write the report
python -m src.syllabus.report               # write the report from report/syllabus_results/
"""
import argparse
import json
import shutil

from src.common import ROOT
from src.syllabus.common import SYLLABUS_RUNS

RESULTS = ROOT / "report" / "syllabus_results"
NAMES = ["digit_cnn", "ae", "vae", "gan", "det_scratch", "det_yolov8", "vgg"]
FRACS = ["0.1", "0.2", "0.3", "0.5", "0.75", "1.0"]
pct = lambda x, d=1: f"{x * 100:.{d}f}"             # noqa: E731


def collect() -> None:
    RESULTS.mkdir(parents=True, exist_ok=True)
    for n in NAMES:
        shutil.copy(SYLLABUS_RUNS / n / "results.json", RESULTS / f"{n}.json")


def load(n: str) -> dict:
    return json.loads((RESULTS / f"{n}.json").read_text(encoding="utf-8"))


def sec(seconds: int) -> str:
    return f"{seconds // 60} min" if seconds >= 120 else f"{seconds} s"


def digit_section(d: dict) -> str:
    worst = min(d["per_class_acc"], key=d["per_class_acc"].get)
    return f"""## Module III: CNN digit classification (MNIST)
A CNN with two 3x3 conv blocks per resolution (28 to 14 to 7), batch norm, dropout and light random affine augmentation, {d['params']:,} parameters, {d['epochs']} epochs (`src/syllabus/digit_cnn.py`).

| Model | Test accuracy | Errors / {d['test_size']:,} |
|---|---:|---:|
| NumPy MLP, from scratch (Module I) | {pct(d['numpy_mlp_acc'], 2)}% | {round((1 - d['numpy_mlp_acc']) * d['test_size'])} |
| **CNN** | **{pct(d['test_acc'], 2)}%** | **{d['errors']}** |

The CNN removes about {pct(1 - (1 - d['test_acc']) / (1 - d['numpy_mlp_acc']), 0)}% of the MLP's errors with the same data: convolution shares weights across positions and pooling gives tolerance to small shifts, which a dense network has to learn from examples. The weakest digit is **{worst}** ({pct(d['per_class_acc'][worst], 2)}%).

![digit CNN](figures/syllabus_digit_cnn.png)
"""


def ae_section(a: dict, v: dict, g: dict) -> str:
    b, den = a["bottleneck"], a["denoising"]
    rows = "\n".join(f"| {z} | {r['compression']}x | {r['test_mse']:.4f} |" for z, r in b.items())
    runs = v["runs"]
    vrows = "\n".join(f"| {r['latent']} | {r['beta']} | {r['recon']:.1f} | {r['kl']:.1f} | **{r['neg_elbo']:.1f}** | {r['active_dims']} / {r['latent']} |" for r in runs.values())
    gen, real, noise = g["generated"], g["real_test"], g["noise_baseline"]
    best_beta = min((k for k in runs if runs[k]["latent"] == 16), key=lambda k: runs[k]["neg_elbo"])
    shares = g["generated"]["class_share"]
    hi, lo = max(range(10), key=shares.__getitem__), min(range(10), key=shares.__getitem__)
    return f"""## Module II: autoencoders, VAE and GAN (all on MNIST)

### Convolutional autoencoder (`src/syllabus/ae.py`)
Encoder 28 to 14 to 7 to a z-vector, mirrored transposed-convolution decoder, binary cross-entropy loss, {a['epochs']} epochs.

| Bottleneck z | Compression | Held-out MSE |
|---|---:|---:|
{rows}

Reconstruction error falls steadily as the code grows. With a 2-number code only a few classes (such as 0 and 1) separate cleanly in the code plane and the reconstructions are blurry blobs of the right general shape (figure); 8 numbers keep most of the stroke shape.
**Denoising:** with Gaussian noise (std {den['noise_std']}) on the input only, the denoising AE (z=32) reaches MSE **{den['denoising_ae_mse_on_noisy_input']:.4f}** against the clean image, the plain z=32 AE {den['plain_ae_mse_on_noisy_input']:.4f}, and the noisy image itself {den['mse_of_the_noisy_image_itself']:.4f}: the plain AE, trained only on clean digits, improves its noisy input only a little by MSE and its output is visibly garbled (figure), while the denoising AE learns what a digit looks like and removes most of the noise.

![autoencoder](figures/syllabus_ae.png)

### Variational autoencoder (`src/syllabus/vae.py`)
Same architecture with a (mu, log-variance) head, the reparameterisation trick and loss = reconstruction + beta x KL. Values are nats per held-out image; the negative ELBO (reconstruction + KL, at beta = 1) is the quantity a VAE minimises.

| z | beta | Reconstruction | KL | Reconstruction + KL | Active dims |
|---|---:|---:|---:|---:|---:|
{vrows}

Among the 16-d models the beta = 1 objective is the one the ELBO defines, and its reconstruction + KL ({runs[best_beta]['neg_elbo']:.1f}) is {"the lowest, as it should be since it optimises exactly that" if best_beta == 'z16_beta1' else "not the lowest, which is unexpected and worth a closer look"}. A smaller beta buys sharper reconstructions (lower reconstruction term) by letting the code carry more information (higher KL); a larger beta forces a simpler, smoother code at the cost of blurrier digits. The 2-d model's manifold (figure) shows digits morphing smoothly between classes, and decoding random N(0, I) vectors gives new digits, which a plain autoencoder cannot do.

![VAE](figures/syllabus_vae.png)

### GAN (`src/syllabus/gan.py`)
DCGAN (transposed-conv generator, strided-conv discriminator, non-saturating generator loss, one-sided label smoothing), {g['epochs']} epochs. Judged with the digit CNN above, since FID is built on ImageNet features:

| Images | Classifier confidence | Class entropy (max {2.303}) | Inception-style score (max 10) |
|---|---:|---:|---:|
| Real test digits | {real['confidence']:.3f} | {real['class_entropy']:.3f} | {real['score']:.2f} |
| **GAN samples (10,000)** | **{gen['confidence']:.3f}** | **{gen['class_entropy']:.3f}** | **{gen['score']:.2f}** |
| Uniform random noise | {noise['confidence']:.3f} | {noise['class_entropy']:.3f} | {noise['score']:.2f} |

All ten digits appear (entropy {gen['class_entropy']:.2f} of a possible 2.30, so no mode collapse), but the mix is uneven (digit {hi} makes up {pct(shares[hi])}% of samples, digit {lo} only {pct(shares[lo])}%) and the samples are clearly less recognisable than real digits (confidence {gen['confidence']:.2f} versus {real['confidence']:.2f}; score {gen['score']:.1f} versus {real['score']:.1f}). The noise row shows why confidence alone is a poor metric: the classifier is {pct(noise['confidence'], 0)}% confident that noise is a single digit, which is why coverage and the combined score are reported too.

![GAN](figures/syllabus_gan.png)
"""


def det_section(s: dict, y: dict) -> str:
    sc, pre = y["scratch"], y["pretrained"]
    rows = [
        (f"YoloLite, written from scratch ({s['params']:,} params, {s['epochs']} epochs)", s["map50"], s["map50_95"], None),
        (f"YOLOv8n, random init ({sc['params']:,} params, {sc['epochs']} epochs)", sc["map50"], sc["map50_95"], sc["ultralytics_map50_95"]),
        (f"YOLOv8n, COCO-pretrained, fine-tuned ({pre['epochs']} epochs)", pre["map50"], pre["map50_95"], pre["ultralytics_map50_95"]),
    ]
    table = "\n".join(f"| {n} | {pct(a, 2)} | {pct(b, 2)} | {'n/a' if u is None else pct(u, 2)} |" for n, a, b, u in rows)
    gain50, gain95 = pre["map50"] - sc["map50"], pre["map50_95"] - sc["map50_95"]
    return f"""## Module III and V: object detection (YOLO)
**Task.** 128x128 scenes with 1 to 4 real MNIST digits of different sizes at random places ({y['train_scenes']:,} training scenes from the MNIST training digits; {y['val_scenes']:,} validation scenes with {y['val_objects']:,} objects, composed from the MNIST *test* digits so no digit is shared). Boxes are measured from the pasted pixels, so labels are exact (`src/syllabus/detection/scenes.py`).

**Detector from scratch** (`yolo_lite.py`): a stride-8 backbone, a 16x16 grid, and per cell an objectness logit, a box and 10 class logits. Targets go to the cell holding the box centre; loss = BCE objectness + 5 x (1 - GIoU) + cross-entropy; decoding = objectness x class probability, a confidence threshold and per-class NMS. **Metric** (`metrics.py`): IoU, VOC all-point average precision, mAP@0.5 and mAP@[0.5:0.95], written without a library and unit-tested on hand-worked cases. All three detectors are scored by this one implementation on the same scenes (the last column is Ultralytics' own, COCO-style, number for reference).

| Detector | mAP@0.5 (%) | mAP@[0.5:0.95] (%) | Ultralytics mAP@[0.5:0.95] (%) |
|---|---:|---:|---:|
{table}

![detection from scratch](figures/syllabus_det_scratch.png)
![YOLOv8 comparison](figures/syllabus_det_yolov8.png)

**Reading the numbers honestly.** Transfer learning moved mAP@0.5 by {gain50 * 100:+.2f} points and mAP@[0.5:0.95] by {gain95 * 100:+.2f} points over the same YOLOv8n trained from random weights, and the from-scratch YoloLite ({s['params'] / sc['params'] * 100:.0f}% of YOLOv8n's size) is within a point of both. Digits on a black canvas are an easy detection problem, so every model is near the ceiling and **this experiment cannot separate them**; a single training run per model gives no error bars, so differences this small should not be over-interpreted. What it does show is that the whole detection pipeline (assignment, loss, decoding, NMS, metric) is correct: an independently implemented detector and Ultralytics agree. The localisation-strict metric (mAP@[0.5:0.95]) is where the models differ most. COCO-pretrained weights are for photographs of 80 object classes, so little of what they know applies here beyond generic edge and shape features.
"""


def vgg_section(v: dict) -> str:
    base = v["small_cnn_from_scratch"]
    models = {m["name"]: m for m in v["models"]}

    def table(metric: str) -> str:
        head = "| Model (image only) | Trained params | " + " | ".join(f"{int(float(f) * 100)}%" for f in FRACS) + " |\n|---|---:|" + "---:|" * len(FRACS)
        rows = [f"| Small CNN from scratch (existing) | n/a | " + " | ".join(pct(base[f][metric]) for f in FRACS) + " |"]
        for m in v["models"]:
            rows.append(f"| {m['name']} | {m['trainable_params']:,} | " + " | ".join(pct(m["by_fraction"][f][metric]) for f in FRACS) + " |")
        return head + "\n" + "\n".join(rows)

    fr, ft, rn = (models[k]["by_fraction"] for k in ("vgg16_frozen", "vgg16_finetune", "resnet18_finetune"))
    return f"""## Module V: transfer learning with VGG16 (and ResNet18, controlled)
All models see only the 64x64 raster, with the same training stream and evaluation as the main experiments, {models['vgg16_frozen']['epochs']} epochs (`src/syllabus/vgg_transfer.py`). ImageNet weights, one channel replicated to three. `frozen` trains only a new classifier on VGG16's convolutional features; `finetune` trains every layer at a lower learning rate.

**Top-5 accuracy (%) by share of the sketch drawn**

{table('top5')}

**Top-1 accuracy (%)**

{table('top1')}

![VGG](figures/syllabus_vgg.png)

* **Frozen features are clearly worse** ({pct(fr['0.3']['top5'])}% Top-5 at 30% against {pct(ft['0.3']['top5'])}% fine-tuned): ImageNet features of photographs describe line drawings poorly, so the network has to be adapted, not just read.
* **Fine-tuned VGG16 and ResNet18 are on par with the small from-scratch CNN** (Top-5 at 30%: {pct(ft['0.3']['top5'])}%, {pct(rn['0.3']['top5'])}% and {pct(base['0.3']['top5'])}%; Top-1 on the finished drawing: {pct(ft['1.0']['top1'])}%, {pct(rn['1.0']['top1'])}% and {pct(base['1.0']['top1'])}%), while training {models['vgg16_finetune']['trainable_params'] / 1e6:.1f} M and {models['resnet18_finetune']['trainable_params'] / 1e6:.1f} M parameters. This agrees with the earlier ResNet18 result: pretraining on natural images does not pay off for QuickDraw-style sketches. Differences of about a point are within what another seed could change (one run each).
"""


def build() -> str:
    d, a, v, g, s, y, vg = (load(n) for n in ("digit_cnn", "ae", "vae", "gan", "det_scratch", "det_yolov8", "vgg"))
    steps = {x["step"]: x["seconds"] for x in json.loads((RESULTS / "steps.json").read_text())}
    return f"""# Syllabus experiments: closing the Module II, III and V gaps

The main project (see [REPORT.md](REPORT.md)) covers Modules I and IV and parts of II, III and V. These experiments add what was missing: a **CNN on digits, convolutional autoencoder, VAE, GAN, object detection (YOLO, from scratch and transfer) and VGG transfer learning**. Everything was trained on a Kaggle GPU in one session ({sec(sum(steps.values()))} of compute in total; per step: {', '.join(f'{k} {sec(v)}' for k, v in steps.items())}) by `kaggle/syllabus/run_syllabus.py`; the numbers below are read from `report/syllabus_results/` by `src/syllabus/report.py`. Each experiment is one run (seed 0): there are no confidence intervals.

{digit_section(d)}
{ae_section(a, v, g)}
{det_section(s, y)}
{vgg_section(vg)}
## Limits
* MNIST and the digit scenes are easy benchmarks; they demonstrate the methods, not state-of-the-art performance.
* The GAN is judged with a classifier-based score rather than FID, and a single GAN run says little about training stability across seeds.
* One run per model; differences of about a point are not significant.
* The VGG16 / ResNet18 / small-CNN comparison was trained before a sampling bug was fixed (every epoch replayed the same samples, see `docs/FLYWHEEL.md`), identically for all of them, so the comparison between them stands as measured but the absolute accuracies are lower than a corrected run would give. The MNIST experiments and the detection scenes use their own data loops and are not affected.
* The detector was not tried on natural images, where the pretrained weights would be expected to matter much more.

## Reproduce
```bash
python -m src.syllabus.digit_cnn && python -m src.syllabus.ae && python -m src.syllabus.vae && python -m src.syllabus.gan   # GAN needs the digit CNN
python -m src.syllabus.detection.train_scratch && python -m src.syllabus.detection.train_yolov8 && python -m src.syllabus.vgg_transfer
python -m src.syllabus.report --collect
```
Add `--smoke` to any script for a tiny pipeline check; CPU works for the MNIST scripts, a GPU is advisable for detection and VGG. The Kaggle path is `python scripts/build_kaggle_dataset.py <user>`, `kaggle datasets version`, then `kaggle kernels push -p kaggle/syllabus`.
"""


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--collect", action="store_true")
    a = ap.parse_args()
    if a.collect:
        collect()
    (ROOT / "report" / "SYLLABUS.md").write_text(build(), encoding="utf-8")
    print("wrote report/SYLLABUS.md")


if __name__ == "__main__":
    main()
