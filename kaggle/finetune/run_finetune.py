"""Kaggle GPU entry point: adapt the live 345-class model to consented user drawings and export the result as a new version.

Normally started by `python -m src.flywheel.cycle`, which fills in NEW_VERSION and the base model below and attaches the inputs:
  * dataset  sketch-evolution-data      the project source (src/)
  * dataset  sketch-evolution-userdata  training.jsonl, the export of consented drawings (python -m app.cli export-training)
  * kernel   the run that trained the base model; its output holds runs/<set>/<architecture>/best.pt
The QuickDraw strokes are downloaded and packed again here (the previous kernel's working files do not carry over).
Outputs in /kaggle/working/out: models/<NEW_VERSION>/*, runs/v3/ft/{best.pt, adaptation.json, results.json}, steps.json, log.txt.
"""
import glob
import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

NEW_VERSION = "v4"                 # replaced by the cycle script when it pushes the kernel
ARCHITECTURE = "fusion_ghost_xl"
BASE_PATH = "runs/v3/fusion_ghost_xl/best.pt"      # the base checkpoint inside the attached kernel's output (replaced by the cycle script)
CLASS_SET = "v3"

WORK = Path("/tmp/proj")
OUT = Path("/kaggle/working/out")
ENV = {**os.environ, "PRESCRIBBLE_CLASS_SET": CLASS_SET}
RUN = "ft"
LOG = OUT / "log.txt"


def run(*args) -> int:
    t0 = time.time()
    OUT.mkdir(parents=True, exist_ok=True)
    print(">>", " ".join(args), flush=True)
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


def find(pattern: str) -> str:
    hits = glob.glob(pattern, recursive=True)
    if not hits:
        raise SystemExit(f"not found: {pattern}")
    return hits[0]


def persist(steps: list[dict]) -> None:
    runs = Path(f"runs/{CLASS_SET}") / RUN
    for rel in (f"models/{NEW_VERSION}", str(runs)):
        folder = WORK / rel
        for f in folder.glob("*") if folder.exists() else []:
            dst = OUT / rel / f.name
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy(f, dst)
    (OUT / "steps.json").write_text(json.dumps(steps, indent=2))


def main() -> None:
    source = Path(find("/kaggle/input/**/src/common.py")).parent.parent
    base = find(f"/kaggle/input/**/{BASE_PATH}")
    users = find("/kaggle/input/**/training.jsonl")
    if WORK.exists():
        shutil.rmtree(WORK)
    shutil.copytree(source, WORK)
    shutil.copy(users, WORK / "training.jsonl")
    subprocess.run([sys.executable, "-m", "pip", "install", "-q", "onnx", "onnxruntime"], check=False)
    plan = [
        ("download", ["-m", "src.data.download", "--mb", "22", "--threads", "8"]),
        ("preprocess", ["-m", "src.data.preprocess", "--packed", "--train", "24000", "--processes", "4"]),
        ("finetune", ["-m", "src.flywheel.finetune", "--base", base, "--user-file", "training.jsonl", "--model", ARCHITECTURE, "--name", RUN,
                      "--epochs", "6", "--epoch-size", "60000"]),
        ("export", ["-m", "src.export.to_onnx", "--model", ARCHITECTURE, "--run", RUN, "--version", NEW_VERSION]),
        ("samples", ["-m", "src.export.samples", "--version", NEW_VERSION]),
    ]
    steps: list[dict] = []
    for name, args in plan:
        t0 = time.time()
        code = run(*args)
        steps.append({"step": name, "exit": code, "seconds": round(time.time() - t0)})
        persist(steps)
        if code != 0:
            print(f"STOPPING: {name} failed", flush=True)
            break
    print("FINETUNE_DONE", flush=True)


if __name__ == "__main__":
    try:
        main()
    except BaseException:
        import traceback

        OUT.mkdir(parents=True, exist_ok=True)
        (OUT / "error.txt").write_text(traceback.format_exc(), encoding="utf-8")
        raise
