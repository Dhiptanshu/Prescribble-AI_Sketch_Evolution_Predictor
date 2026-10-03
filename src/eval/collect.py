"""Merge every runs/<model>/results.json into models/<version>/results.json (the UI reads real numbers only).

python -m src.eval.collect [--version v1]
"""
import argparse
import json

from src.common import ROOT, RUNS_DIR

ORDER = ["mlp", "cnn", "lstm", "fusion", "fusion_ghost", "resnet_ghost"]


def main(version: str = "v1"):
    merged = {}
    for name in ORDER:
        p = RUNS_DIR / name / "results.json"
        if p.exists():
            merged[name] = json.load(open(p))
    out = ROOT / "models" / version / "results.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    json.dump(merged, open(out, "w"), indent=1)
    print("collected:", list(merged))


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--version", default="v1")
    main(ap.parse_args().version)
