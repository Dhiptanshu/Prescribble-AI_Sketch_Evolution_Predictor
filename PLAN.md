# Sketch Evolution Predictor — Project Plan

**Course:** Deep Learning Laboratory (2604733), GLS FET B.Tech CS&E, Sem VII
**One-liner:** A live drawing canvas that guesses what you are drawing after only 20–30% of the ink is down, shows its Top-5 guesses evolving stroke by stroke, and paints a faint "ghost" of how it expects the drawing to finish.

---

## STATUS UPDATE: product build started (paused after Phase 1 core)
The lab project below is complete. Work then moved to a SaaS-style product (accounts, API, web app): see [docs/PRODUCT_PLAN.md](docs/PRODUCT_PLAN.md)
for the roadmap and progress, and [docs/DEVELOPMENT.md](docs/DEVELOPMENT.md) for how to run it.

## STATUS (Fri 2 Oct 2026): lab project build complete

Done and verified: 30-class stroke data pipeline, NumPy MLP (MNIST 97.85%), CNN / LSTM / fusion / ghost / ResNet18 models trained on Kaggle GPU,
ONNX export (4.8 ms CPU, ~18 ms in browser), browser demo (free draw, AI challenge, replay of real test sketches), report, figures, five module notebooks,
IMDB sentiment LSTM (85.67%), USB bundle (superseded: the legacy `demo/` was retired; use `scripts/make_web_bundle.py`, see docs/LAB.md). Headline: Top-5 90.6% at 20% of the ink, 94.3% at 30%.
GAN, VAE, YOLO detection, VGG, conv AE and the digit CNN were added afterwards as separate experiments on a Kaggle GPU (3 Oct 2026): see [report/SYLLABUS.md](report/SYLLABUS.md). Not done: a sketch multi-object scene mode in the app, and VAE/GAN ghost completion. Still to do: rehearse on a real lab machine (Ubuntu, Firefox/Chromium), prepare slides from `report/`.
See [report/REPORT.md](report/REPORT.md) for results and honest limitations.

---

## 0. REVISED: 2-day schedule (deadline Sunday 4 Oct 2026)

The 40-session timeline in §10 is replaced by this compressed one. Solo, working locally (16 cores, no GPU) with Kaggle available for heavy runs.

**Scope decisions (to finish properly instead of half-finishing everything):**
- **30 classes**, ~3.8k sketches each (3200 train / 300 val / 300 test).
- **Core (must ship):** data pipeline → NumPy MLP + MNIST → CNN → LSTM → CNN+LSTM fusion with ghost-completion head → ResNet18 transfer-learning comparison → accuracy-vs-completion curves → live demo (Flask + browser-only mode) → report/slides.
- **Cut:** GAN, YOLO/multi-object scene mode. Listed as future work. VAE only if time remains.
- **Sentiment analysis:** small separate IMDB-LSTM notebook, done last.

| When | Work | Done when |
|---|---|---|
| **Fri evening** | Scaffold, download + preprocess data, partial-sketch generator, NumPy MLP + MNIST | Can render any sketch at any % ; MNIST ≥ 97% |
| **Sat morning** | CNN, LSTM, fusion + ghost head training scripts; MLP baseline on sketches | All models train; first curves |
| **Sat afternoon** | Train all variants, ResNet18 transfer learning (local or Kaggle), evaluation + ablation figures, ONNX export | Final model chosen, <50 ms CPU |
| **Sat night** | Demo app: Flask server mode + browser-only (ONNX Runtime Web) mode, real-user test drawings | Demo works on your laptop |
| **Sun morning** | Lab compatibility test (Ubuntu venv path + browser path), README, report, slides, sentiment notebook | Everything packaged on USB |
| **Sun** | Buffer, rehearsal | |

---

## 1. What makes it different

Most QuickDraw projects classify a finished 28×28 bitmap. This one is about **earliness**:

| Feature | Why it is interesting |
|---|---|
| **Accuracy-vs-completion curve** (headline result) | Top-1/Top-5 accuracy at 10%, 20%, …, 100% of the sketch. Nobody reports this; it is a clear, graphable result. |
| **Ghost completion** | A decoder predicts the finished drawing from the partial one and overlays it in light grey while you draw. Visually striking, and it is where Autoencoder/VAE/GAN (Module II) naturally fit. |
| **Multiple plausible endings (VAE)** | Sampling the latent space shows 3 different ways the sketch could finish when the model is unsure. |
| **Confidence timeline** | A live line chart of the Top-5 probabilities per stroke: "when does the model commit?" |
| **Human vs AI mode** | You draw a prompted object, the AI races to guess it. Score = how early it is right. Good for a live audience. |
| **Uncertainty indicator** | Prediction entropy drives a "thinking / sure" cue. |

## 2. Syllabus mapping (40 sessions, 5 modules, 20% each)

The five modules become five build stages of one system, so each lab session produces a piece of the final project.

| Module | Sessions | Syllabus topic | Project component | Deliverable |
|---|---|---|---|---|
| **I** | 1–8 | NN, MLP, feedforward + backprop, MNIST | Data pipeline + **MLP from scratch in NumPy** (manual backprop), MNIST warm-up, then MLP baseline on flattened partial sketches | Baseline accuracy-vs-completion curve |
| **II** | 9–16 | AE, VAE, Conv-AE, GAN | **Conv-AE / VAE "sketch completer"**: partial → full image (ghost). Optional conditional GAN to sharpen strokes | Ghost-completion model, latent-space samples |
| **III** | 17–24 | CNN, digit classification, object detection | **CNN classifier** on rasterized partials. Detection session: **multi-object canvas** (see §5) | Main image-branch classifier |
| **IV** | 25–32 | RNN, LSTM, sentiment analysis | **LSTM/GRU over the pen-stroke sequence**, then **CNN+LSTM fusion** | Fusion model, ablation table |
| **V** | 33–40 | Transfer learning: YOLO, VGG, ResNet | Fine-tune **ResNet18 / VGG16 / MobileNetV2** on partial sketches vs training from scratch; final model selection, export, demo, report | Transfer-learning comparison, final app |

**Two honest gaps to settle with your faculty:**
1. *"Neural sentiment analysis" (sessions 29–32)* is text, not sketches. Either (a) submit a small separate sentiment-LSTM notebook (IMDB, about 1 session of work) as a lab file alongside the project, or (b) accept the sequence-modeling work as covering Module IV. Option (a) is safer for the internal practical exam.
2. *YOLO* is a detector. For classification of sketches, VGG/ResNet/MobileNet are the right transfer-learning backbones. Use YOLO only in the multi-object scene mode (§5) and label it clearly.

Also note CO2 says "real time applications" and the course objective says "build and deploy end-to-end", so the live demo directly serves the grading criteria.

## 3. Data

- **Source:** Google QuickDraw, *simplified* `.ndjson` files (raw stroke coordinates). The 28×28 `.npy` bitmaps are **not enough**, because partial sketches need stroke order.
- **Scope:** **50 classes** chosen for demo appeal and a mix of easy and confusable pairs (cat/dog, sun/flower, house/castle, cup/mug). Per class: 5k train / 500 val / 500 test, `recognized == true` only. About 300 MB after trimming.
- **Download:** stream only the first ~6k lines of each class file. No need for the multi-GB full set. Cache locally, and copy the processed `.npz` onto a USB stick.
- **Licence:** QuickDraw is CC BY 4.0. Cite it in the report.

### Partial-sketch generation (the core trick)
- Cut the drawing at a random **fraction of total ink length** (arc length), not stroke count. Many sketches have only 2–4 strokes, so "20% of strokes" is too coarse. Cutting mid-stroke is allowed and realistic.
- Training samples p ~ Uniform(10%, 100%), with extra weight on 15–40%. Evaluation uses fixed p ∈ {10, 20, 30, 50, 75, 100}.
- Each sketch yields two views: **raster** (64×64, strokes drawn as lines) and **sequence** (stroke-3 `[dx, dy, pen_lift]`, max length ~100).

### The normalisation trap (design decision)
QuickDraw scales each *finished* drawing to fill a 256×256 box. A live user's unfinished drawing has no final bounding box. So:
- Train and infer in a **fixed 256×256 frame**: cut the prefix of the *already-normalised* drawing and do **not** re-normalise the prefix.
- Add random scale/translate/rotate augmentation to the whole drawing *before* cutting, so a user who draws small or off-centre still works.
- The live canvas shows a faint guide box and tells the user to "draw big".

### Live-vs-dataset domain shift
QuickDraw drawers used phones and fast mouse strokes. Lab drawers will use a mouse or touchpad. Mitigate with: Ramer–Douglas–Peucker simplification at inference (matches the "simplified" data), point jitter augmentation, and **testing early on real hand-drawn samples** from you and your team (collect ~20 per class as a small "real-user" test set).

## 4. Model architecture

**Final model: dual-branch + multitask**

```
 partial strokes ──┬─ raster 64×64 ─► CNN (or pretrained ResNet18) ─► f_img ─┐
                   │                                                         ├─► concat ─► MLP ─► Top-5 logits (50)
                   └─ stroke-3 seq ─► GRU/LSTM (2 layers, 128) ─► f_seq ────┘
                                                         │
                                                         └─► conv decoder ─► completed 64×64 image (ghost)
```

- **Loss:** cross-entropy + λ·reconstruction (BCE/L1 on the full image). The ghost decoder also acts as a regulariser for the classifier.
- **Variants for the ablation table** (this is the evaluation content for the report):
  1. MLP on flattened raster (Module I baseline)
  2. CNN only
  3. LSTM only
  4. CNN + LSTM fusion
  5. Fusion + completion head
  6. Fusion with pretrained ResNet18/VGG16/MobileNetV2 image branch (fine-tuned)
- **Ghost variants:** Conv-AE (deterministic) → VAE (diverse samples) → optional cGAN refinement. Pick by visual quality and training time, then report all three honestly.
- **Real-time constraint:** the final model must run in **under ~50 ms per prediction on a CPU**. This is a hard design limit, so keep the image branch small (custom CNN or MobileNetV2/ResNet18 at 64×64).

## 5. Object-detection session (Module III, sessions 23–24)

Keep it modest and honest: **multi-object scene mode**. Group strokes by spatial proximity or time gap into objects, put a bounding box on each, and run the predictor per group, so you can draw a house and a sun side by side and see two labelled boxes. Optional extension: fine-tune YOLOv8-nano on canvases composed from real QuickDraw sketches (composition of real data, not fabricated labels). Drop it if time is short; it is not on the critical path.

## 6. Evaluation plan

- **Primary:** Top-1 and Top-5 accuracy vs completion % (line chart, one line per model).
- **Earliness:** mean completion % at which the true class first enters and *stays* in Top-5.
- **Others:** confusion matrix at 25% vs 100% (shows which classes are inherently ambiguous early), calibration (ECE), reconstruction MSE/SSIM for the ghost, inference latency on CPU.
- **Real-user test set** (your own drawings) reported separately from QuickDraw test accuracy. Expect a drop, and say so.
- **Targets (aspirational, to be validated, not promised):** Top-5 ≥ 60% at 25% completion, ≥ 90% at 100%. Final numbers come from the experiments, whatever they are.

## 7. Compute and tooling

| Decision | Choice | Reason |
|---|---|---|
| Framework | **PyTorch** (NumPy for Module I) | Syllabus says "TensorFlow and PyTorch". The training loops here (GAN, multitask, custom sequence handling) are simpler in PyTorch, and native Windows TF has had no GPU support since 2.10. |
| Training machine | **Kaggle GPU notebooks** (T4/P100, ~30 GPU-hrs/week). Laptop is used only for development, small tests and the demo. Your laptop torch is CPU-only (`2.9.1+cpu`), which is fine under this plan. | 50 classes × 5k at 64×64 trains in minutes to tens of minutes per model. Kaggle has CUDA PyTorch preinstalled, and QuickDraw is already hosted there as a Kaggle dataset, so no manual download is needed. |
| Export | `torch.onnx.export` → **ONNX Runtime (CPU)** | Tiny runtime, no PyTorch needed on the lab machine. |
| Demo UI | **Flask + plain HTML/JS canvas** (Chart.js for the timeline) | Minimal dependencies, works in any browser, low latency. Streamlit's canvas is too laggy for per-stroke live prediction. |
| Experiment tracking | CSV logs + saved matplotlib figures | No accounts or internet needed. |

## 8. Running in the college lab (the risky part)

Known: lab machines run **Ubuntu**, are on a **LAN**, and you *might* get install rights. Unknown: Ubuntu/Python version (22.04 → Python 3.10, 24.04 → 3.12), whether the LAN reaches the internet, GPU (assume none).

1. **Plan A: your own laptop** on the lab projector. Zero lab dependence. Verify the HDMI/adapter early.
2. **Plan B: zero-install browser page (promoted to the main lab plan).** Run the ONNX models in the browser with **ONNX Runtime Web (WASM)**. The lab PC only needs a browser (Firefox/Chrome); copy the folder from a USB stick and open `index.html` (or `python3 -m http.server`, since Ubuntu ships Python 3). This is OS-independent, so the Ubuntu-vs-Windows difference no longer matters. Build it early, since it is the likeliest to work on any machine.
3. **Plan C: Python venv install** (`python3 -m venv`, `pip install onnxruntime flask numpy`) if install rights and internet exist. A Linux wheelhouse can be prepared on your laptop with `pip download --platform manylinux2014_x86_64 --python-version <lab version> --only-binary=:all:` once you know the lab's Python version, for offline use.
4. **Plan D: laptop as server over the LAN.** Run Flask on your laptop and open `http://<laptop-ip>:5000` from the lab PC's browser. This works only if the LAN does not isolate clients, so test it, but never rely on it alone.
5. **Plan E: recorded demo video** plus slides with all result figures, as a last resort.

Rules: no downloads at presentation time, no cloud dependency, test on one actual lab machine a few days before. Sketch input in the browser should use Pointer Events so mouse, touchpad and touchscreen all work.

Note: because Plan B needs the model to run in-browser, keep the final model small (<10 MB) and use only ONNX ops that onnxruntime-web supports (standard conv/GRU/linear are fine; verify early by loading the ONNX in the browser around session 9).

## 9. Repository layout

```
Sketch_Evolution_DLL/
├── PLAN.md
├── README.md
├── requirements.txt            # training env
├── requirements-demo.txt       # lab runtime (onnxruntime, flask, numpy, cv2-headless)
├── data/                       # raw ndjson (gitignored), processed .npz
├── src/
│   ├── data/    download.py, preprocess.py, partial.py, dataset.py
│   ├── models/  mlp_numpy.py, cnn.py, lstm.py, fusion.py, autoencoder.py, vae.py, gan.py, transfer.py
│   ├── train/   train_classifier.py, train_completer.py
│   ├── eval/    curves.py, confusion.py, realuser.py
│   └── export/  to_onnx.py
├── notebooks/                  # one per module (lab-file friendly)
├── demo/                       # Flask app, static/ canvas JS, models/*.onnx
├── report/                     # figures, report draft, slides
└── scripts/                    # run_demo.bat, build_bundle.ps1
```

Each module gets a self-contained notebook so it also works as the per-session lab record for the internal exam.

## 10. Timeline by session

| Sessions | Work | Exit criterion |
|---|---|---|
| 1–2 | Env setup (CUDA torch venv), download 50 classes, preprocess, partial-sketch generator, visual sanity check | Can render any sketch at any % |
| 3–6 | NumPy MLP with manual backprop; MNIST 97%+ | MNIST result in notebook |
| 7–8 | MLP baseline on partial sketches → first accuracy-vs-completion curve | Curve figure exists |
| 9–12 | Conv-AE then VAE completion | Ghost images look plausible at 30% |
| 13–16 | Conv-AE polish, latent sampling, optional cGAN | Module II notebook done |
| 17–22 | CNN classifier, tuning, augmentation, MNIST/digit task for syllabus | Beats MLP baseline clearly |
| 23–24 | Multi-object scene mode (or minimal detection demo) | Two objects detected on a canvas |
| 25–28 | Stroke-sequence LSTM/GRU | LSTM curve |
| 29–32 | Fusion + completion head; sentiment-LSTM side notebook if required | Ablation table v1 |
| 33–38 | Transfer learning (ResNet18/VGG16/MobileNetV2) vs scratch | Comparison table |
| 39 | Pick final model, ONNX export, latency test | <50 ms CPU |
| 40 | Demo polish, lab dry run, report, slides | Dry run on a lab PC |

**Demo UI can start as early as session 9** using any model (even the MLP), then swap models in as they improve. Do this: a working demo early removes the biggest risk.

## 11. Risks

| Risk | Mitigation |
|---|---|
| Live drawings differ from QuickDraw | Fixed-frame training, augmentation, real-user test set, guide box |
| Lab machine cannot run the demo | Plans A–D in §8 |
| Training too slow | Cap at 50 classes / 5k each; CUDA venv; Colab fallback; small models |
| Ghost completion looks blurry | Expected from AE/VAE. Present it as "expected shape", add cGAN only if time permits |
| Top-5 at 25% lower than hoped | Report the curve honestly; the ambiguity analysis is itself a finding |
| Scope creep (GAN, YOLO, scene mode) | Mark them as stretch goals; the core is data → CNN → LSTM → fusion → demo |

## 12. Presentation flow (about 10 min)

1. **Hook (1 min):** you draw 3 strokes, the AI already shows "cat?".
2. **Problem and novelty (1 min):** earliness rather than final accuracy.
3. **Data and the partial-sketch idea (1.5 min):** the fixed-frame trick.
4. **Architecture (2 min):** one diagram, tied to the five syllabus modules.
5. **Results (2 min):** accuracy-vs-completion curve, ablation, transfer-learning comparison.
6. **Live demo (2 min):** the Human-vs-AI race with an audience volunteer.
7. **Limits and future work (0.5 min).**

## 13. Open questions for you

Answered: PyTorch is OK; lab is Ubuntu with LAN and possibly install rights; sentiment analysis as a separate notebook is OK; training on Kaggle GPU.

Still open:
1. **Team size and deadline** (how many sessions remain, and is there a submission date earlier than session 40)?
2. **Lab Ubuntu/Python version and whether the LAN reaches the internet** (ask the lab admin; decides Plan B vs C).
3. **Number of classes:** 50 is the default. Happy to go 30 for speed or 100 for impressiveness.

## 14. Kaggle workflow

- Your `~/.kaggle/access_token` exists, but the `kaggle` CLI is **not installed** on the laptop yet (`pip install kaggle`).
- Flow: write code locally in `src/`, push it to a **private Kaggle dataset** (or a GitHub repo cloned inside the notebook), run training in a Kaggle notebook with GPU, save checkpoints and ONNX files to `/kaggle/working`, then download them with `kaggle kernels output`.
- Attach a QuickDraw dataset from Kaggle's catalogue or upload your own preprocessed `.npz` (about 300 MB) as a private dataset. **Check that the chosen Kaggle dataset has stroke-level data, not just bitmaps.** If not, download the official `.ndjson` files from inside the notebook (needs the notebook's Internet toggle on, which requires a phone-verified account).
- Kaggle sessions cap at about 9–12 hours and files outside `/kaggle/working` vanish, so save a checkpoint every epoch and make training scripts resumable.
- Keep the same code runnable on CPU with a tiny subset, so you can debug locally before spending GPU quota.
