"""Kaggle GPU entry point: train the 100-class model (class set v2) from scratch and export it as models/v2.

Everything happens in the kernel: download the QuickDraw stroke files of the 100 classes (the kernel has internet), preprocess, train the deployed
architecture (CNN + LSTM + ghost decoder), export to ONNX, write the sample sketches. Outputs go to /kaggle/working/out/{models/v2, runs/v2}.
The project source comes from the private dataset `sketch-evolution-data` (see scripts/build_kaggle_dataset.py).
"""
import glob
import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

WORK = Path("/tmp/proj")                      # not under /kaggle/working: the 1 GB of raw data must not become kernel output
OUT = Path("/kaggle/working/out")
ENV = {**os.environ, "PRESCRIBBLE_CLASS_SET": "v2"}
EPOCHS, EPOCH_SIZE = "25", "150000"


LOG = OUT / "log.txt"


def run(*args) -> int:
    """Run one step, echo its output to the kernel log AND keep a copy in out/log.txt (so a failure can be read afterwards)."""
    t0 = time.time()
    print(">>", " ".join(args), flush=True)
    OUT.mkdir(parents=True, exist_ok=True)
    with open(LOG, "a", encoding="utf-8") as log:
        log.write(f">> {' '.join(args)}" + chr(10))
        proc = subprocess.Popen([sys.executable, *args], cwd=WORK, env=ENV, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1)
        for line in proc.stdout:
            print(line, end="", flush=True)
            log.write(line)
            log.flush()
        code = proc.wait()
    print(f"<< exit {code} in {time.time() - t0:.0f}s", flush=True)
    return code


def persist(steps: list[dict]) -> None:
    for rel, patterns in (("models/v2", ["*"]), ("runs/v2", ["*/best.pt", "*/log.csv", "*/results.json"])):
        for pattern in patterns:
            for f in (WORK / rel).glob(pattern):
                dst = OUT / rel / f.relative_to(WORK / rel)
                dst.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy(f, dst)
    (OUT / "steps.json").write_text(json.dumps(steps, indent=2))


def export_heldout(per_class: int = 100) -> None:
    """The first `per_class` test sketches of every class (never trained on by any model of either generation): the shared yardstick the
    registry's promotion gate and the comparison tool use. Written to out/heldout_v2.pkl."""
    import pickle

    import numpy as np

    sys.path.insert(0, str(WORK))
    os.environ["PRESCRIBBLE_CLASS_SET"] = "v2"
    from src.common import CLASSES, DATA_DIR

    sketches, labels = pickle.load(open(DATA_DIR / "sketches.pkl", "rb"))["test"]
    keep = np.concatenate([np.flatnonzero(labels == c)[:per_class] for c in range(len(CLASSES))])
    OUT.mkdir(parents=True, exist_ok=True)
    pickle.dump({"sketches": [sketches[i] for i in keep], "labels": labels[keep], "classes": CLASSES}, open(OUT / "heldout_v2.pkl", "wb"), protocol=4)
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
        ("download", ["-m", "src.data.download", "--mb", "12"]),
        ("preprocess", ["-m", "src.data.preprocess", "--train", "6000", "--val", "300", "--test", "300"]),
        ("train", ["-m", "src.train.train", "--model", "fusion_ghost", "--epochs", EPOCHS, "--epoch-size", EPOCH_SIZE, "--bs", "256",
                   "--workers", "4", "--threads", "4", "--lr", "3e-3"]),
        ("export", ["-m", "src.export.to_onnx", "--model", "fusion_ghost", "--version", "v2"]),
        ("samples", ["-m", "src.export.samples", "--version", "v2"]),
        ("heldout", None),
    ]
    for name, args in plan:
        t0 = time.time()
        code = run(*args) if args else (export_heldout() or 0)
        steps.append({"step": name, "exit": code, "seconds": round(time.time() - t0)})
        persist(steps)
        if code != 0:
            print(f"STOPPING: {name} failed", flush=True)
            break
    print("V2_DONE", flush=True)


if __name__ == "__main__":
    try:
        main()
    except BaseException:                                   # leave the reason in the output, then fail loudly
        import traceback

        OUT.mkdir(parents=True, exist_ok=True)
        (OUT / "error.txt").write_text(traceback.format_exc(), encoding="utf-8")
        raise
