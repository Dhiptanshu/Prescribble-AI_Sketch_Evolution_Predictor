"""Kaggle GPU entry point: adapt the 100-class model (v2) to consented user drawings and measure the gain on held-out real drawings.

Inputs (attach them to the kernel):
  * dataset  sketch-evolution-data      the project source (src/) and the v1 sketches
  * dataset  sketch-evolution-userdata  a private dataset holding training.jsonl, the export of consented drawings
                                        (python -m app.cli export-training --out training.jsonl)
  * kernel   sketch-evolution-v2        its output holds runs/v2/fusion_ghost/best.pt, the base model
Everything the v2 run did (download, preprocess) is repeated here because /kaggle/working does not carry over between kernels.
Outputs: /kaggle/working/out/{runs/v2/<name>/{best.pt,adaptation.json,results.json}, models/<version>, log.txt}.
"""
import glob
import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

WORK = Path("/tmp/proj")
OUT = Path("/kaggle/working/out")
ENV = {**os.environ, "PRESCRIBBLE_CLASS_SET": "v2"}
NAME = "fusion_ghost_ft"
NEW_VERSION = os.environ.get("NEW_VERSION", "v3")


def run(*args) -> int:
    t0 = time.time()
    OUT.mkdir(parents=True, exist_ok=True)
    print(">>", " ".join(args), flush=True)
    with open(OUT / "log.txt", "a", encoding="utf-8") as log:
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


def main() -> None:
    src_root = Path(find("/kaggle/input/**/src/common.py")).parent.parent
    base = find("/kaggle/input/**/runs/v2/fusion_ghost/best.pt")
    users = find("/kaggle/input/**/training.jsonl")
    if WORK.exists():
        shutil.rmtree(WORK)
    shutil.copytree(src_root, WORK)
    subprocess.run([sys.executable, "-m", "pip", "install", "-q", "onnx", "onnxruntime"], check=False)
    steps = []
    plan = [
        ("download", ["-m", "src.data.download", "--mb", "12"]),
        ("preprocess", ["-m", "src.data.preprocess", "--train", "6000", "--val", "300", "--test", "300"]),
        ("finetune", ["-m", "src.flywheel.finetune", "--base", base, "--user-file", users, "--name", NAME, "--epochs", "6", "--epoch-size", "60000"]),
        ("export", ["-m", "src.export.to_onnx", "--model", "fusion_ghost", "--run", NAME, "--version", NEW_VERSION]),
        ("samples", ["-m", "src.export.samples", "--version", NEW_VERSION]),
    ]
    for name, args in plan:
        t0 = time.time()
        code = run(*args)
        steps.append({"step": name, "exit": code, "seconds": round(time.time() - t0)})
        for rel in (f"runs/v2/{NAME}", f"models/{NEW_VERSION}"):
            for f in (WORK / rel).glob("*") if (WORK / rel).exists() else []:
                dst = OUT / rel / f.name
                dst.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy(f, dst)
        (OUT / "steps.json").write_text(json.dumps(steps, indent=2))
        if code != 0:
            print(f"STOPPING: {name} failed", flush=True)
            break
    print("FINETUNE_DONE", flush=True)


if __name__ == "__main__":
    main()
