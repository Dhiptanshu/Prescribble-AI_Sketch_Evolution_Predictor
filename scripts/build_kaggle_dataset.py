"""Stage src/ + the processed sketches into kaggle/dataset/ for `kaggle datasets create/version`.

python scripts/build_kaggle_dataset.py <kaggle-username>
"""
import json
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
STAGE = ROOT / "kaggle" / "dataset"


def main(user: str):
    if STAGE.exists():
        shutil.rmtree(STAGE)
    shutil.copytree(ROOT / "src", STAGE / "src", ignore=shutil.ignore_patterns("__pycache__"))
    (STAGE / "data" / "processed").mkdir(parents=True)
    shutil.copy(ROOT / "data" / "processed" / "sketches.pkl", STAGE / "data" / "processed" / "sketches.pkl")
    meta = {"title": "Sketch Evolution Data", "id": f"{user}/sketch-evolution-data", "licenses": [{"name": "other"}],
            "description": "Derived from Google QuickDraw (CC BY 4.0) plus the project source code."}
    json.dump(meta, open(STAGE / "dataset-metadata.json", "w"), indent=2)
    print("staged", STAGE)


if __name__ == "__main__":
    main(sys.argv[1])
