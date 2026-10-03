# The model flywheel (Phase 6)

```
people draw  ->  consented, confirmed drawings  ->  export  ->  retrain / fine-tune on Kaggle  ->  compare on held-out drawings
     ^                                                                                                      |
     +----  the app and the widget load whatever models/registry.json says is live  <--  promote (gated)  <-+
```

## 1. Where the data comes from (privacy rules, all enforced in code and tests)
A drawing is **training-ready** only when all of these hold (`apps/api/app/services/training_data.py`):
* its owner has **training consent on right now** (off by default; switching it off removes their drawings from every later export),
* the **label is confirmed by the person** (the Studio's checkbox "I checked: this label is right", picking a label, or a Teach word). The AI's own guess, saved without checking, is never a label,
* the label is a class of the live model, and the drawing is not an exact duplicate.

Two sources: ordinary saved drawings, and the **Teach the AI** page (`/teach`): after explicit consent, the person is given the word the model has the *fewest* examples of and draws it. Each contribution records which pointer drew it (mouse, touch or pen, reported by the browser), because the gap between QuickDraw's phone sketches and mouse drawings is the problem this loop exists to close. Contributions stay out of the gallery and stats, have their own cap (`MAX_TEACH_PER_USER`), and can be deleted in one click (`DELETE /api/v1/teach/contributions`).

Classroom drawings are never training data: students have no account and gave no consent.

## 2. Export
```bash
cd apps/api
python -m app.cli export-training --out training.jsonl      # classes of the live model; --version vN for another
```
One JSON object per line: `uid, label, strokes, source, input_type, model_version, created`. No account identity: the `uid` is a one-way hash of the drawing id. The same uid always falls on the same side of the **train / held-out split** (`src/flywheel/dataset.py`: one in five is held out), so a drawing used to evaluate is never used to train, across exports. The admin dashboard shows how much is ready (by class and pointer type).

## 3. Model registry (`models/registry.json`)
```bash
python -m src.flywheel.registry list
python -m src.flywheel.registry register v2 --parent v1
python -m src.flywheel.registry promote v2 --heldout data/processed/v2/heldout.pkl [--user-eval training.jsonl]
python -m src.flywheel.registry rollback
```
* A registered version folder is **immutable** (its ONNX hash is stored and re-checked on every promotion and rollback).
* **Promotion is gated** (`src/flywheel/gate.py`): the candidate must load and answer a real sample with a probability vector, must not drop a class the live model knows, and must not be worse than the live model, within a tolerance, on held-out sketches of the classes both know (Top-5 averaged over 20 / 30 / 50 % of the ink; both models restricted to the shared classes so a 100-class model is not penalised for knowing more). If at least 30 held-out **real user drawings** exist, the same test runs on them as a second gate. `--force` overrides and is recorded in the history.
* **The apps follow the registry**, so a new version ships with no app change: the API reads `active` (`PRESCRIBBLE_MODEL_VERSION` pins one), and the web app and the widget fetch `models/registry.json` (never cached) before loading the model. After a promotion call `POST /api/v1/admin/model/reload` (admin) to switch a running API without a restart. A challenge day or classroom round that already started keeps scoring with its own model.
* `GET /api/v1/models` lists the versions with their measured numbers.

## 4. Retraining on Kaggle
* `kaggle/flywheel/run_v2.py`: downloads the QuickDraw stroke files of the 100-class set (`src/classsets.py`, `PRESCRIBBLE_CLASS_SET=v2`), preprocesses, trains the deployed architecture, exports `models/v2` and the held-out evaluation sketches.
* `kaggle/flywheel/run_finetune.py`: fine-tunes v2 on the consented drawings (`src/flywheel/finetune.py`), and measures **before and after on the held-out real drawings and on QuickDraw** (so forgetting shows), then exports the new version.
Recipe: `python scripts/build_kaggle_dataset.py <user>`, `kaggle datasets version ...`, `kaggle kernels push -p kaggle/flywheel`. Put `training.jsonl` in a private dataset `sketch-evolution-userdata` for the fine-tune kernel.

## 5. Results so far (3 Oct 2026)
**v2, the 100-class model** (trained from scratch on a Kaggle GPU, 25 epochs, 150k sketches per epoch, 6000 training sketches per class; training log `docs/results/v2_training_log.csv`). On its own QuickDraw test set (100 classes, 300 sketches each): Top-5 **79.7%** with 30% of the ink drawn and **95.5%** on the finished drawing; Top-1 on the finished drawing 78.8%. That is a harder task than v1's 30 classes (v1: 94.3% Top-5 at 30%, 91.6% Top-1 finished), as the lab report predicted.

**Promotion gate v1 to v2** (`docs/results/gate_v1_to_v2.json`, 900 held-out sketches of the 30 shared classes, neither model trained on them): with both models restricted to the 30 shared classes, Top-5 averaged over 20/30/50% of the ink is **92.8% for v1 and 91.9% for v2** (difference -0.9 points, inside the 1-point tolerance, and about the size of the sampling noise at n = 900). If v2 must choose among all 100 classes the same sketches get 79.4%. No class was dropped, so the gate passed.

**Decision left to the owner:** the gate passing means v2 *may* go live, not that it should: for people drawing the original 30 objects v2 is a little worse when restricted and clearly worse when it must also rule out 70 other objects, in exchange for recognising 70 more. v1 is live (v2 was promoted by the gate during testing and rolled back; both events are in `models/registry.json` history). `python -m src.flywheel.registry promote v2 --heldout data/processed/v2/heldout.pkl` plus `POST /api/v1/admin/model/reload` makes it live again; the app was checked with v2 in a real browser (100 label choices, sensible Top-5, confidence chart fine).

## 6. Honest limits
* **No real-user gain has been measured yet**: that needs real drawings (nobody has taught the AI yet, so the fine-tuning was only smoke-tested on v1's own QuickDraw samples, whose numbers mean nothing). The machinery (collection, export, mixing, before / after, gate) is built and tested; the number appears when people have taught the AI. Fine-tune results below 30 held-out real drawings are refused as evidence.
* The held-out split is by drawing, not by person, so one person's style can appear on both sides; with few contributors the measured gain is optimistic.
* The registry file is a plain file in the repo's `models/` folder: one operator at a time, no locking.
* One API process keeps the live scorer in memory; several replicas each need the reload call.
