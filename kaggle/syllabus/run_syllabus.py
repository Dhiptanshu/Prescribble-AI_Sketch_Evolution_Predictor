"""Kaggle GPU entry point for the syllabus experiments (Modules II, III, V). Each step runs in its own process; a failure never stops the next step.

The private dataset `sketch-evolution-data` holds src/ (including src/syllabus), data/processed/sketches.pkl and two small result files
(see scripts/build_kaggle_dataset.py). MNIST and the ImageNet / COCO weights are downloaded here (the kernel has internet on).
Outputs: /kaggle/working/out/{runs/syllabus/..., report/figures/syllabus_*.png, steps.json}; the session log is the kernel log.
"""
import glob
import json
import shutil
import subprocess
import sys
import time
from pathlib import Path

WORK = Path("/kaggle/working/proj")
OUT = Path("/kaggle/working/out")

# Order: cheap and independent first. digit_cnn must precede gan (the GAN is scored with that classifier).
STEPS = [
    ("digit_cnn", ["-m", "src.syllabus.digit_cnn", "--epochs", "15"]),
    ("ae", ["-m", "src.syllabus.ae", "--epochs", "15"]),
    ("vae", ["-m", "src.syllabus.vae", "--epochs", "20"]),
    ("gan", ["-m", "src.syllabus.gan", "--epochs", "30"]),
    ("det_scratch", ["-m", "src.syllabus.detection.train_scratch", "--epochs", "40", "--train", "20000", "--val", "2000"]),
    ("det_yolov8", ["-m", "src.syllabus.detection.train_yolov8", "--epochs", "30", "--train", "20000", "--val", "2000"]),
    ("vgg", ["-m", "src.syllabus.vgg_transfer", "--epochs", "8", "--epoch-size", "60000", "--workers", "4"]),
]


def persist():
    for sub in ("runs/syllabus", "report/figures"):
        src, dst = WORK / sub, OUT / sub
        if src.exists():
            shutil.copytree(src, dst, dirs_exist_ok=True, ignore=shutil.ignore_patterns("*.pt", "weights", "*.png" if sub == "runs/syllabus" else "~"))
    for pt in (WORK / "runs/syllabus").glob("*/*.pt"):               # small weights worth keeping (the classifier and the generator)
        if pt.stat().st_size < 30_000_000 and pt.parent.name in ("digit_cnn", "gan"):
            (OUT / "runs/syllabus" / pt.parent.name).mkdir(parents=True, exist_ok=True)
            shutil.copy(pt, OUT / "runs/syllabus" / pt.parent.name / pt.name)


def main():
    hits = glob.glob("/kaggle/input/**/src/common.py", recursive=True)
    if not hits:
        for z in glob.glob("/kaggle/input/**/*.zip", recursive=True):
            shutil.unpack_archive(z, "/kaggle/working/unzipped")
        hits = glob.glob("/kaggle/working/unzipped/**/src/common.py", recursive=True)
    src = Path(hits[0]).parent.parent
    if WORK.exists():
        shutil.rmtree(WORK)
    shutil.copytree(src, WORK)
    for rel in ("runs/cnn/results.json", "runs/mlp_mnist/results.json"):
        have = glob.glob(f"/kaggle/input/**/{rel}", recursive=True) + glob.glob(f"/kaggle/working/unzipped/**/{rel}", recursive=True)
        if have:
            (WORK / rel).parent.mkdir(parents=True, exist_ok=True)
            shutil.copy(have[0], WORK / rel)

    subprocess.run([sys.executable, "-m", "pip", "install", "-q", "ultralytics"], check=False)
    import torch
    print("cuda:", torch.cuda.is_available(), torch.cuda.get_device_name(0) if torch.cuda.is_available() else "", flush=True)

    steps = []
    for name, args in STEPS:
        t0 = time.time()
        print(f">> {name}: {' '.join(args)}", flush=True)
        code = subprocess.run([sys.executable, *args], cwd=WORK).returncode
        steps.append({"step": name, "exit": code, "seconds": round(time.time() - t0)})
        print(f"<< {name} exit {code} in {time.time() - t0:.0f}s", flush=True)
        persist()
        (OUT / "steps.json").write_text(json.dumps(steps, indent=2))
    print("SYLLABUS_DONE", flush=True)


if __name__ == "__main__":
    main()
