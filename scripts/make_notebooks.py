"""Build one lab notebook per syllabus module in notebooks/ (they read the real runs, nothing is mocked).

python scripts/make_notebooks.py
Execute them afterwards with:  jupyter nbconvert --to notebook --execute --inplace notebooks/*.ipynb
"""
from pathlib import Path

import nbformat as nbf

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "notebooks"

SETUP = """import sys, json, os
from pathlib import Path
ROOT = Path.cwd().parent if Path.cwd().name == "notebooks" else Path.cwd()
sys.path.insert(0, str(ROOT)); os.chdir(ROOT)
import numpy as np, matplotlib.pyplot as plt, inspect
plt.rcParams.update({"figure.dpi": 110, "axes.spines.top": False, "axes.spines.right": False})
res = lambda m: json.load(open(ROOT / "runs" / m / "results.json"))"""

CURVE = """def curve(models, metric="top5"):
    fig, ax = plt.subplots(figsize=(6.5, 3.8))
    for m, label in models.items():
        r = res(m); xs = sorted(r, key=float)
        ax.plot([float(x) * 100 for x in xs], [r[x][metric] * 100 for x in xs], marker="o", label=label)
    ax.set(xlabel="% of sketch drawn", ylabel=f"{metric} accuracy (%)"); ax.grid(alpha=.25); ax.legend(frameon=False); plt.show()"""

NOTEBOOKS = {
    "1_neural_networks.ipynb": [
        ("md", "# Module I: Neural networks, MLP, backpropagation, MNIST\nA multilayer perceptron written **from scratch in NumPy** (manual forward pass and backpropagation), then reused as the baseline for partial sketches."),
        ("code", SETUP + "\nfrom src.models.mlp_numpy import MLP\nprint(inspect.getsource(MLP.step))"),
        ("md", "## Backpropagation check\nThe analytic gradient from `step` must match a numerical (finite-difference) gradient."),
        ("code", "rng = np.random.default_rng(0)\nx = rng.random((16, 20)).astype('float32'); y = rng.integers(0, 5, 16)\nnet = MLP([20, 12, 8, 5], seed=1)\na, n = net.grad_check(x, y, eps=1e-2)\nprint('analytic', np.round(a, 5)); print('numeric ', np.round(n, 5)); print('max abs diff', float(np.abs(a - n).max()))"),
        ("md", "## Digit classification on MNIST\nA short training run here (3 epochs); the full 12-epoch run result is shown below it."),
        ("code", "import torchvision\nds = torchvision.datasets.MNIST(ROOT / 'data' / 'processed' / 'mnist', train=True, download=True)\nts = torchvision.datasets.MNIST(ROOT / 'data' / 'processed' / 'mnist', train=False, download=True)\nX = ds.data.numpy().reshape(-1, 784).astype('float32') / 255; Y = ds.targets.numpy()\nXt = ts.data.numpy().reshape(-1, 784).astype('float32') / 255; Yt = ts.targets.numpy()\nnet = MLP([784, 256, 128, 10], lr=0.05)\nnet.fit(X, Y, epochs=3, on_epoch=lambda e, l: print(f'epoch {e} loss {l:.4f} test acc {net.accuracy(Xt, Yt):.4f}'))"),
        ("code", "print('Full run (12 epochs, Kaggle):', res('mlp_mnist'))"),
        ("md", "## Same network on partial sketches (baseline)\nA 1024-512-256-30 MLP on 32x32 rasters of partial QuickDraw sketches."),
        ("code", CURVE + "\ncurve({'mlp': 'MLP (NumPy)'})\nr = res('mlp'); print({k: round(v['top5'], 3) for k, v in r.items()}, '(top-5)')"),
    ],
    "2_autoencoders_ghost.ipynb": [
        ("md", "# Module II: Autoencoders (the sketch 'ghost')\nThe ghost decoder is an encoder-decoder trained to reconstruct the **completed** drawing from a **partial** one. It uses transposed convolutions and a skip connection from the partial input."),
        ("code", SETUP + "\nfrom src.models.nets import GhostDecoder\nprint(inspect.getsource(GhostDecoder))"),
        ("md", "## What the decoder predicts (held-out test sketches, 30% drawn)\nTop row: what the user has drawn. Middle: the model's ghost (an expected-ink heat map). Bottom: the real finished sketch."),
        ("code", "from IPython.display import Image\nImage(str(ROOT / 'report' / 'figures' / 'ghost_gallery.png'))"),
        ("md", "The ghost is a *mean* prediction: where the object is ambiguous (e.g. a lone circle), it spreads ink over the plausible endings. That blur is the model's uncertainty, not a bug."),
        ("code", "r = res('fusion_ghost')\nprint({k: round(v['ghost_bce'], 4) for k, v in r.items()}, '<- test reconstruction BCE per pixel by completion fraction')"),
    ],
    "3_cnn.ipynb": [
        ("md", "# Module III: Convolutional neural networks\nA CNN classifier on rasterised partial sketches (64x64), compared with the MLP baseline. Below, the trained CNN is run on real held-out test sketches."),
        ("code", SETUP + "\nfrom src.models.nets import CNNEncoder\nprint(inspect.getsource(CNNEncoder))"),
        ("code", CURVE + "\ncurve({'mlp': 'MLP (NumPy)', 'cnn': 'CNN'})"),
        ("md", "## Live predictions on held-out sketches (30% drawn)"),
        ("code", "import torch\nfrom src.models.nets import build\nfrom src.data.dataset import eval_set, as_float\nfrom src.common import CLASSES\nnet = build('cnn'); net.load_state_dict(torch.load(ROOT / 'runs' / 'cnn' / 'best.pt', map_location='cpu')); net.eval()\nd = eval_set('test')[0.3]\nidx = np.arange(0, len(d['y']), 1100)[:8]\nb = as_float({k: v[idx] for k, v in d.items()})\nwith torch.no_grad(): p = torch.softmax(net(b['img'], b['seq'], b['len'])[0], 1)\nfig, ax = plt.subplots(1, 8, figsize=(15, 2.4))\nfor k in range(8):\n    top = p[k].topk(3)\n    ax[k].imshow(b['img'][k, 0], cmap='gray'); ax[k].axis('off')\n    ax[k].set_title(f\"true: {CLASSES[b['y'][k]]}\\n\" + '\\n'.join(f'{CLASSES[i]} {v:.0%}' for v, i in zip(top.values, top.indices)), fontsize=8)\nplt.show()"),
    ],
    "4_lstm_sequences.ipynb": [
        ("md", "# Module IV: Recurrent networks and LSTM\nSketches are *sequences* of pen points, so an LSTM can read them as they are drawn. Here the LSTM alone, then fused with the CNN. A second task, neural **sentiment analysis**, uses an LSTM on IMDB reviews."),
        ("code", SETUP + "\nfrom src.models.nets import LSTMEncoder, SketchNet\nprint(inspect.getsource(LSTMEncoder))"),
        ("code", CURVE + "\ncurve({'cnn': 'CNN', 'lstm': 'LSTM', 'fusion': 'CNN + LSTM'})"),
        ("code", "for m in ['cnn', 'lstm', 'fusion']:\n    r = res(m); print(f\"{m:7s} top-5 @20%: {r['0.2']['top5']:.3f}   @30%: {r['0.3']['top5']:.3f}   top-1 @30%: {r['0.3']['top1']:.3f}\")"),
        ("md", "## Sentiment analysis (IMDB, LSTM)"),
        ("code", "p = ROOT / 'runs' / 'sentiment' / 'results.json'\nprint(json.load(open(p)) if p.exists() else 'run: python -m src.train.sentiment_lstm')\nfrom src.train.sentiment_lstm import SentimentLSTM\nprint(inspect.getsource(SentimentLSTM))"),
    ],
    "5_transfer_learning.ipynb": [
        ("md", "# Module V: Transfer learning\nAn ImageNet-pretrained **ResNet18** (first layer adapted to 1-channel input) replaces the small CNN and is fine-tuned together with the LSTM and ghost decoder. We compare it with the same architecture using a CNN trained from scratch."),
        ("code", SETUP + "\nfrom src.models.nets import ResNetEncoder\nprint(inspect.getsource(ResNetEncoder))"),
        ("code", CURVE + "\ncurve({'fusion_ghost': 'CNN from scratch + LSTM + ghost', 'resnet_ghost': 'ResNet18 (ImageNet) + LSTM + ghost'})\ncurve({'fusion_ghost': 'CNN from scratch + LSTM + ghost', 'resnet_ghost': 'ResNet18 (ImageNet) + LSTM + ghost'}, 'top1')"),
        ("code", "import csv\nfor m in ['fusion_ghost', 'resnet_ghost']:\n    rows = list(csv.DictReader(open(ROOT / 'runs' / m / 'log.csv')))\n    print(f\"{m}: {len(rows)} epochs, ~{np.mean([float(r['secs']) for r in rows]):.0f} s/epoch on the Kaggle GPU, best val mean top-1 {max(float(r['val_mean_top1']) for r in rows):.3f}\")"),
        ("md", "## Finding\nTransfer learning did **not** beat the small CNN trained from scratch here: line drawings are far from ImageNet photographs, and the larger network costs more time per epoch. This is a genuine negative result and is reported as such."),
    ],
}


def main():
    OUT.mkdir(exist_ok=True)
    for name, cells in NOTEBOOKS.items():
        nb = nbf.v4.new_notebook()
        nb.cells = [nbf.v4.new_markdown_cell(c) if k == "md" else nbf.v4.new_code_cell(c) for k, c in cells]
        nb.metadata["kernelspec"] = {"name": "python3", "display_name": "Python 3", "language": "python"}
        nbf.write(nb, OUT / name)
        print("wrote", name)


if __name__ == "__main__":
    main()
