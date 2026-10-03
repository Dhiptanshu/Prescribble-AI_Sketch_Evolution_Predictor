"""Kaggle GPU entry point: train the 345-class model (class set v3: every QuickDraw category) with the wide architecture, and export it as models/v3.

In the kernel: download the first 22 MB of every category's stroke file (about 7.6 GB, threaded), pack up to 24,000 training drawings per class into
memory-mapped uint8 arrays (src/data/packed.py), train `fusion_ghost_xl`, export to ONNX, write the sample sketches, the held-out evaluation set
and the per-class accuracies. Outputs go to /kaggle/working/out/{models/v3, runs/v3, heldout_v3.pkl, steps.json, log.txt}.
The project source comes from the private dataset `sketch-evolution-data` (scripts/build_kaggle_dataset.py).
"""
import glob
import json
import os
import pickle
import shutil
import subprocess
import sys
import threading
import time
from pathlib import Path

WORK = Path("/tmp/proj")                      # raw data and caches stay out of /kaggle/working, which becomes the kernel's output
OUT = Path("/kaggle/working/out")
ENV = {**os.environ, "PRESCRIBBLE_CLASS_SET": "v3"}
MODEL = "fusion_ghost_xl"
EPOCHS, EPOCH_SIZE = "40", "300000"
LOG = OUT / "log.txt"


def run(*args) -> int:
    """Run one step, echo its output to the kernel log AND keep a copy in out/log.txt (so a failure can be read afterwards)."""
    t0 = time.time()
    print(">>", " ".join(args), flush=True)
    OUT.mkdir(parents=True, exist_ok=True)
    with open(LOG, "a", encoding="utf-8") as log:
        log.write(">> " + " ".join(args) + chr(10))
        proc = subprocess.Popen([sys.executable, *args], cwd=WORK, env=ENV, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1)
        for line in proc.stdout:
            print(line, end="", flush=True)
            log.write(line)
            log.flush()
        code = proc.wait()
    print(f"<< exit {code} in {time.time() - t0:.0f}s", flush=True)
    return code


def persist(steps: list[dict] | None = None) -> None:
    for rel, patterns in (("models/v3", ["*"]), ("runs/v3", [f"{MODEL}/best.pt", f"{MODEL}/log.csv", f"{MODEL}/results.json"])):
        for pattern in patterns:
            for f in (WORK / rel).glob(pattern):
                dst = OUT / rel / f.relative_to(WORK / rel)
                dst.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy(f, dst)
    if steps is not None:
        (OUT / "steps.json").write_text(json.dumps(steps, indent=2))


def keep_copying(stop: threading.Event) -> None:
    """Every few minutes, copy the best checkpoint and the training log to the output, so a killed session still leaves a usable model."""
    while not stop.wait(300):
        try:
            persist()
        except Exception as e:  # noqa: BLE001  (a copy hiccup must never stop the training)
            print("periodic copy failed:", e, flush=True)


def export_heldout(per_class: int = 50) -> None:
    """The first `per_class` test drawings of every class: the held-out yardstick for the registry's promotion gate (the test drawings
    are the same positions the 100-class model's were, which v1 and v2 never trained on)."""
    import numpy as np

    sys.path.insert(0, str(WORK))
    os.environ["PRESCRIBBLE_CLASS_SET"] = "v3"
    from src.common import CLASSES
    from src.data.dataset import load_splits

    sketches, labels = load_splits()["test"]
    keep = np.concatenate([np.flatnonzero(labels == c)[:per_class] for c in range(len(CLASSES))])
    OUT.mkdir(parents=True, exist_ok=True)
    pickle.dump({"sketches": [sketches[int(i)] for i in keep], "labels": labels[keep], "classes": CLASSES}, open(OUT / "heldout_v3.pkl", "wb"), protocol=4)
    print(f"held-out set: {len(keep)} sketches", flush=True)


def main() -> None:
    hits = glob.glob("/kaggle/input/**/src/common.py", recursive=True)
    if not hits:
        for z in glob.glob("/kaggle/input/**/*.zip", recursive=True):
            shutil.unpack_archive(z, "/kaggle/working/unzipped")
        hits = glob.glob("/kaggle/working/unzipped/**/src/common.py", recursive=True)
    if WORK.exists():
        shutil.rmtree(WORK)
    shutil.copytree(Path(hits[0]).parent.parent, WORK)
    subprocess.run([sys.executable, "-m", "pip", "install", "-q", "onnx", "onnxruntime"], check=False)
    steps: list[dict] = []
    plan = [
        ("download", ["-m", "src.data.download", "--mb", "22", "--threads", "8"]),
        ("preprocess", ["-m", "src.data.preprocess", "--packed", "--train", "24000", "--processes", "4"]),
        ("train", ["-m", "src.train.train", "--model", MODEL, "--epochs", EPOCHS, "--epoch-size", EPOCH_SIZE, "--bs", "256", "--workers", "4",
                   "--threads", "4", "--lr", "3e-3"]),
        ("export", ["-m", "src.export.to_onnx", "--model", MODEL, "--version", "v3"]),
        ("samples", ["-m", "src.export.samples", "--version", "v3"]),
        ("heldout", None),
    ]
    stop = threading.Event()
    threading.Thread(target=keep_copying, args=(stop,), daemon=True).start()
    for name, args in plan:
        t0 = time.time()
        code = run(*args) if args else (export_heldout() or 0)
        steps.append({"step": name, "exit": code, "seconds": round(time.time() - t0)})
        persist(steps)
        if code != 0:
            print(f"STOPPING: {name} failed", flush=True)
            break
    stop.set()
    print("V3_DONE", flush=True)


if __name__ == "__main__":
    try:
        main()
    except BaseException:                                   # leave the reason in the output, then fail loudly
        import traceback

        OUT.mkdir(parents=True, exist_ok=True)
        (OUT / "error.txt").write_text(traceback.format_exc(), encoding="utf-8")
        raise
