"""Kaggle GPU entry point: trains every variant sequentially and leaves results in /kaggle/working/runs.

The private dataset `sketch-evolution-data` holds src/ and data/processed/sketches.pkl (see scripts/build_kaggle_dataset.py).
A failure in one model never stops the others.
"""
import glob
import shutil
import subprocess
import sys
import time
from pathlib import Path

WORK = Path("/kaggle/working/proj")
OUT = Path("/kaggle/working/runs")

# (model, epochs). The deployed model goes first so it is safe even if the session is cut short.
PLAN = [("fusion_ghost", 20), ("cnn", 16), ("lstm", 16), ("fusion", 16), ("resnet_ghost", 12)]


def run(cmd):
    print(">>", " ".join(cmd), flush=True)
    t = time.time()
    r = subprocess.run(cmd, cwd=WORK)
    print(f"<< exit {r.returncode} in {time.time() - t:.0f}s", flush=True)
    return r.returncode


def main():
    hits = glob.glob("/kaggle/input/**/src/common.py", recursive=True)
    if not hits:  # dataset delivered as zips: unpack them next to where they were mounted
        for z in glob.glob("/kaggle/input/**/*.zip", recursive=True):
            shutil.unpack_archive(z, "/kaggle/working/unzipped")
        hits = glob.glob("/kaggle/working/unzipped/**/src/common.py", recursive=True)
    print("input tree:", sorted(glob.glob("/kaggle/input/**", recursive=True))[:30], flush=True)
    src = Path(hits[0]).parent.parent
    if WORK.exists():
        shutil.rmtree(WORK)
    shutil.copytree(src, WORK)
    (WORK / "runs").mkdir(exist_ok=True)

    for model, epochs in PLAN:
        run([sys.executable, "-m", "src.train.train", "--model", model, "--epochs", str(epochs),
             "--bs", "256", "--epoch-size", "100000", "--workers", "4", "--threads", "4", "--lr", "3e-3"])
        shutil.copytree(WORK / "runs", OUT, dirs_exist_ok=True)   # persist after every model

    run([sys.executable, "-m", "src.train.mlp_baseline", "sketch"])
    run([sys.executable, "-m", "src.train.mlp_baseline", "mnist"])
    shutil.copytree(WORK / "runs", OUT, dirs_exist_ok=True)
    print("DONE", flush=True)


if __name__ == "__main__":
    main()
