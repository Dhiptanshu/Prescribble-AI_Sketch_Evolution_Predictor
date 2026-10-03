# Prescribble

*The AI that guesses your drawing before you finish it.* It reads your strokes as you draw, names what it thinks it is, and paints how it
expects the drawing to end. The model runs entirely in the browser (about 20 ms per update), so drawings stay private unless you save them.

Started as the Deep Learning Laboratory project (GLS FET, 2604733) on Google QuickDraw (30 classes, stroke-level data) and is growing into a
product: accounts, saved drawings, a public API and classrooms. See [docs/PRODUCT_PLAN.md](docs/PRODUCT_PLAN.md) for the roadmap and progress.

| Top-5 accuracy (held-out test sketches) | 10% drawn | 20% | 30% | 50% | 100% |
|---|---:|---:|---:|---:|---:|
| Deployed model (CNN + LSTM + ghost) | 77.6 | 90.6 | 94.3 | 97.0 | 98.8 |

Full results, ablations and limitations: [report/REPORT.md](report/REPORT.md); the VAE / GAN / YOLO / VGG / digit-CNN experiments: [report/SYLLABUS.md](report/SYLLABUS.md). Original lab plan and syllabus mapping: [PLAN.md](PLAN.md).

## Quick start
```bash
npm install && pip install -r apps/api/requirements-dev.txt
cd apps/api && python -m uvicorn app.main:create_app --factory --port 8100     # API  (http://localhost:8100/api/docs)
npm run dev:web                                                                # app  (http://localhost:5173)
```
More (single-origin mode, Docker, migrations, configuration): [docs/DEVELOPMENT.md](docs/DEVELOPMENT.md).

## Run it on a machine with only a browser and Python 3 (e.g. a college lab)
```bash
npm run build:web && python scripts/make_web_bundle.py      # -> dist/prescribble-web.zip (~20 MB)
python scripts/verify_web_bundle.py                         # self-check: unzips it, serves it, probes every file
```
Copy the zip to a USB stick, unzip, run `bash run.sh` (Linux/macOS) or `run.bat` (Windows). No pip, no internet, no GPU, no backend:
the app starts in offline mode (the Studio works fully; accounts need the server). Step-by-step runbook: [docs/LAB.md](docs/LAB.md).

## Repository layout
```
apps/api/        FastAPI service: auth, migrations, rate limits, serves the built web app
apps/web/        React + TypeScript + Vite app (landing, Studio, auth) and a stdlib static server (serve.py)
packages/engine/ TypeScript stroke pipeline + ONNX Runtime Web wrapper (golden-tested against the Python pipeline)
models/<ver>/    versioned model artefacts: sketch.onnx, meta.json, results.json, samples.json
src/             ML research code: data pipeline, models, training, evaluation, export
kaggle/          GPU training driver and dataset staging
notebooks/       one lab notebook per syllabus module
report/          results report, figures
deploy/          Dockerfile and docker-compose
docs/            product plan, development guide, lab runbook
scripts/         bundle, fixtures, notebooks and dataset helpers
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
# Syllabus gaps (Kaggle GPU run, see report/SYLLABUS.md): CNN on digits, conv AE, VAE, GAN, YOLO detection, VGG16 transfer
python -m src.syllabus.digit_cnn                  # Module III   (then ae, vae, gan, detection.train_scratch, detection.train_yolov8, vgg_transfer)
python -m src.train.sentiment_lstm                # Module IV (sentiment analysis)
python -m src.eval.collect && python -m src.export.samples
python -m src.export.to_onnx --model fusion_ghost          # writes models/v1 (use --version v2 for a new model)
python -m src.eval.analysis && python -m src.eval.report
```
Training on a CPU is slow (a full fusion epoch takes about 25 minutes on a laptop), so the reported runs used a Kaggle GPU:
`python scripts/build_kaggle_dataset.py <user>`, then `kaggle datasets create` and `kaggle kernels push -p kaggle/kernel`.

## Tests
```bash
cd apps/api && python -m pytest -q      # API
npm test && npm run typecheck && npm run lint
python -m pytest tests -q               # ML pipeline geometry
```

Data: Google QuickDraw, CC BY 4.0.
