# Sketch Evolution Predictor

Predicts what you are drawing from the first 20–30% of your strokes, shows its Top-5 guesses evolving live,
and paints a "ghost" of how it expects the drawing to end. Built for the Deep Learning Laboratory (GLS FET, 2604733)
on Google QuickDraw (30 classes, stroke-level data). Everything runs in the browser, in about 20 ms per update.

| Top-5 accuracy (held-out test sketches) | 10% drawn | 20% | 30% | 50% | 100% |
|---|---:|---:|---:|---:|---:|
| Deployed model (CNN + LSTM + ghost) | 77.6 | 90.6 | 94.3 | 97.0 | 98.8 |

Full results, ablations, limitations: [report/REPORT.md](report/REPORT.md). Design and syllabus mapping: [PLAN.md](PLAN.md).

## Run the demo (laptop or lab machine)

The demo is a static page. The model runs **inside the browser** (ONNX Runtime Web), so the lab PC only needs a browser
and Python 3 (preinstalled on Ubuntu). No pip install, no internet, no GPU.

```bash
python scripts/make_bundle.py     # first time on a fresh clone: copies models/v1 into demo/models and builds the zip
bash demo/run.sh              # Ubuntu/Linux/macOS: starts the server and opens the browser
python3 demo/serve.py         # or manually, then open http://localhost:8765
```

Windows: double-click `demo\run.bat`, or `python demo\serve.py`.

**For the lab:** `python scripts/make_bundle.py` creates `dist/sketch-evolution-demo.zip` (about 30 MB). Copy it to a USB stick,
unzip it on the lab machine and run `bash run.sh`. If port 8765 is busy, pass another: `bash run.sh 9000`.

## Project layout

```
src/
  common.py            constants (classes, frame, image size)
  data/                download.py, preprocess.py, partial.py (cut/render/sequence), dataset.py
  models/              mlp_numpy.py (from scratch), nets.py (CNN, LSTM, fusion, ghost decoder, ResNet18)
  train/               train.py (any variant), mlp_baseline.py (MNIST + sketch baseline), sentiment_lstm.py (IMDB)
  eval/                collect.py (results for the UI), analysis.py (figures), report.py (REPORT.md)
  export/              to_onnx.py, samples.py
demo/                  index.html, static/{css,js}, vendor/ort, models/ (onnx + real results), run.sh, run.bat, serve.py
kaggle/                GPU training driver (kernel/) and dataset staging
notebooks/             one lab notebook per syllabus module
report/                REPORT.md, figures/, analysis.json
scripts/               build_kaggle_dataset.py, make_bundle.py, make_notebooks.py
tests/                 geometry tests for the partial-sketch pipeline
```

## Reproduce the experiments

```bash
pip install -r requirements.txt
python -m src.data.download && python -m src.data.preprocess
python -m src.train.mlp_baseline mnist            # Module I
python -m src.train.mlp_baseline sketch
python -m src.train.train --model cnn             # Module III
python -m src.train.train --model lstm            # Module IV
python -m src.train.train --model fusion
python -m src.train.train --model fusion_ghost    # Module II (ghost decoder)
python -m src.train.train --model resnet_ghost    # Module V (transfer learning)
python -m src.train.sentiment_lstm                # Module IV (sentiment analysis)
python -m src.eval.collect && python -m src.export.samples
python -m src.export.to_onnx --model fusion_ghost
python -m src.eval.analysis && python -m src.eval.report
```

Training on a CPU is slow (a full fusion epoch takes about 25 minutes on a laptop), so the reported runs used a Kaggle GPU:
`python scripts/build_kaggle_dataset.py <user>`, then `kaggle datasets create` and `kaggle kernels push -p kaggle/kernel`.

## Tests

```bash
python -m pytest tests -q
```

Data: Google QuickDraw, CC BY 4.0.
