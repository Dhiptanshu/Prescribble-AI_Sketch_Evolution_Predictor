"""Generate and execute the three syllabus-gap notebooks (notebooks/2b_*, 3b_*, 5b_*).

python scripts/make_syllabus_notebooks.py
Notebooks read report/syllabus_results/ and report/figures/ (committed), show the real model code, and run small live cells (build the models,
compose real scenes). Narrative stays short and points at report/SYLLABUS.md, where every sentence is generated from the same results.
"""
from pathlib import Path

import nbformat as nbf
from nbclient import NotebookClient

ROOT = Path(__file__).resolve().parent.parent
SETUP = '''import sys, os, json, inspect
from pathlib import Path
ROOT = Path.cwd().parent if Path.cwd().name == "notebooks" else Path.cwd()
sys.path.insert(0, str(ROOT)); os.chdir(ROOT)
import numpy as np, matplotlib.pyplot as plt, matplotlib.image as mpimg
plt.rcParams.update({"figure.dpi": 110, "axes.spines.top": False, "axes.spines.right": False})
res = lambda n: json.load(open(ROOT / "report" / "syllabus_results" / f"{n}.json"))
def show(name, width=15):
    img = mpimg.imread(ROOT / "report" / "figures" / f"syllabus_{name}.png")
    plt.figure(figsize=(width, width * img.shape[0] / img.shape[1])); plt.imshow(img); plt.axis("off"); plt.show()
'''


def nb(cells):
    n = nbf.v4.new_notebook()
    n.metadata["kernelspec"] = {"display_name": "Python 3", "language": "python", "name": "python3"}
    n.cells = [nbf.v4.new_markdown_cell(c) if k == "md" else nbf.v4.new_code_cell(c) for k, c in cells]
    return n


NOTEBOOKS = {
    "2b_autoencoder_vae_gan.ipynb": [
        ("md", "# Module II (completed): convolutional autoencoder, VAE and GAN\nAll three on MNIST, trained on a Kaggle GPU (`kaggle/syllabus/run_syllabus.py`). Numbers below are read from `report/syllabus_results/`; the written analysis is in `report/SYLLABUS.md`."),
        ("code", SETUP),
        ("md", "## Convolutional autoencoder\nThe model, then the bottleneck study and the denoising result."),
        ("code", "from src.syllabus.ae import ConvAE\nprint(inspect.getsource(ConvAE))\nprint('parameters for z = 2, 8, 32:', [sum(p.numel() for p in ConvAE(z).parameters()) for z in (2, 8, 32)])"),
        ("code", "a = res('ae')\nfor z, r in a['bottleneck'].items(): print(f\"z={z:>2}  compression {r['compression']:>6}x   held-out MSE {r['test_mse']:.4f}\")\nprint('denoising (noise std 0.5):', {k: round(v, 4) for k, v in a['denoising'].items() if k != 'noise_std'})\nshow('ae')"),
        ("md", "## Variational autoencoder\nThe loss is where it differs from the plain AE: reconstruction plus a KL term that keeps the code close to N(0, I)."),
        ("code", "from src.syllabus.vae import ConvVAE, loss_terms\nprint(inspect.getsource(loss_terms)); print(inspect.getsource(ConvVAE.forward))"),
        ("code", "v = res('vae')\nprint(f\"{'run':<14}{'recon':>8}{'KL':>8}{'-ELBO':>9}{'active dims':>13}\")\nfor name, r in v['runs'].items(): print(f\"{name:<14}{r['recon']:>8.1f}{r['kl']:>8.1f}{r['neg_elbo']:>9.1f}{r['active_dims']:>8} / {r['latent']}\")\nshow('vae')"),
        ("md", "## GAN (DCGAN)\nJudged with the digit CNN from the Module III notebook: classifier confidence, class entropy (mode coverage) and an Inception-style score."),
        ("code", "from src.syllabus.gan import Generator, Discriminator\nprint(inspect.getsource(Generator)); print('G params', sum(p.numel() for p in Generator().parameters()), ' D params', sum(p.numel() for p in Discriminator().parameters()))"),
        ("code", "g = res('gan')\nfor k in ('real_test', 'generated', 'noise_baseline'): print(f\"{k:<15}\", {m: round(x, 3) for m, x in g[k].items() if m != 'class_share'})\nshow('gan')"),
    ],
    "3b_digits_and_detection.ipynb": [
        ("md", "# Module III (completed): CNN digit classification and object detection\nA CNN on MNIST digits, then a YOLO-style detector written from scratch on scenes of real digits. Results from `report/syllabus_results/`; analysis in `report/SYLLABUS.md`."),
        ("code", SETUP),
        ("md", "## CNN on handwritten digits"),
        ("code", "from src.syllabus.digit_cnn import DigitCNN\nprint(inspect.getsource(DigitCNN))\nd = res('digit_cnn')\nprint(f\"CNN {d['test_acc']*100:.2f}% ({d['errors']} errors / {d['test_size']})   NumPy MLP {d['numpy_mlp_acc']*100:.2f}%   parameters {d['params']:,}\")\nshow('digit_cnn')"),
        ("md", "## Detection scenes: real MNIST digits composed on a canvas\nThe boxes are measured from the pasted pixels. These four scenes are generated right now from the real MNIST test digits (green = ground truth)."),
        ("code", "from matplotlib.patches import Rectangle\nfrom src.syllabus.detection.scenes import build_scenes\nimgs, boxes = build_scenes(4, 'val')\nfig, axs = plt.subplots(1, 4, figsize=(13, 3.4))\nfor ax, im, bx in zip(axs, imgs, boxes):\n    ax.imshow(im, cmap='gray'); ax.axis('off')\n    for c, x1, y1, x2, y2 in bx:\n        ax.add_patch(Rectangle((x1, y1), x2 - x1, y2 - y1, fill=False, ec='#22c55e', lw=1.6)); ax.text(x1, y1 - 2, str(int(c)), color='#22c55e')\nplt.show()"),
        ("md", "## The detector, its loss and the metric (written from scratch)"),
        ("code", "from src.syllabus.detection import yolo_lite, metrics\nprint(inspect.getsource(yolo_lite.YoloLite)); print(inspect.getsource(yolo_lite.giou)); print(inspect.getsource(yolo_lite.yolo_loss)); print(inspect.getsource(metrics.average_precision))"),
        ("code", "s = res('det_scratch')\nprint(f\"YoloLite  mAP@0.5 {s['map50']*100:.2f}%   mAP@[0.5:0.95] {s['map50_95']*100:.2f}%   {s['params']:,} parameters   {s['val_objects']} validation objects\")\nshow('det_scratch')"),
    ],
    "5b_vgg_and_yolo_transfer.ipynb": [
        ("md", "# Module V (completed): transfer learning with VGG16 and YOLOv8\nTwo controlled comparisons. Results from `report/syllabus_results/`; analysis in `report/SYLLABUS.md`."),
        ("code", SETUP),
        ("md", "## VGG16 on partial sketches (image only), against ResNet18 and a small CNN from scratch"),
        ("code", "from src.syllabus.vgg_transfer import ImageNetBackbone\nprint(inspect.getsource(ImageNetBackbone))"),
        ("code", "v = res('vgg'); F = ['0.1', '0.2', '0.3', '0.5', '0.75', '1.0']\nprint(f\"{'Top-5 %':<22}\" + ''.join(f'{int(float(f)*100):>7}%' for f in F))\nprint(f\"{'small CNN (scratch)':<22}\" + ''.join(f\"{v['small_cnn_from_scratch'][f]['top5']*100:>8.1f}\" for f in F))\nfor m in v['models']: print(f\"{m['name']:<22}\" + ''.join(f\"{m['by_fraction'][f]['top5']*100:>8.1f}\" for f in F) + f\"   ({m['trainable_params']:,} trained params)\")\nshow('vgg', 13)"),
        ("md", "## YOLOv8n: COCO-pretrained against random initialisation, on the digit scenes\nSame architecture, data, epochs and metric; the only difference is the starting weights. Our from-scratch detector is included for reference."),
        ("code", "y = res('det_yolov8'); s = res('det_scratch')\nprint(f\"{'detector':<28}{'mAP@0.5':>9}{'mAP@.5:.95':>12}\")\nprint(f\"{'YoloLite (ours)':<28}{s['map50']*100:>9.2f}{s['map50_95']*100:>12.2f}\")\nfor m in ('scratch', 'pretrained'): print(f\"{'YOLOv8n ' + m:<28}{y[m]['map50']*100:>9.2f}{y[m]['map50_95']*100:>12.2f}\")\nshow('det_yolov8', 11)"),
    ],
}


def main():
    for name, cells in NOTEBOOKS.items():
        n = nb(cells)
        NotebookClient(n, timeout=600, kernel_name="python3", resources={"metadata": {"path": str(ROOT / "notebooks")}}).execute()
        nbf.write(n, ROOT / "notebooks" / name)
        print("wrote", name)


if __name__ == "__main__":
    main()
