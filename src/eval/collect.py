"""Merge every runs/<model>/results.json into demo/models/results.json (the UI reads real numbers only).

python -m src.eval.collect
"""
import json

from src.common import ROOT, RUNS_DIR

ORDER = ["mlp", "cnn", "lstm", "fusion", "fusion_ghost", "resnet_ghost"]


def main():
    merged = {}
    for name in ORDER:
        p = RUNS_DIR / name / "results.json"
        if p.exists():
            merged[name] = json.load(open(p))
    out = ROOT / "demo" / "models" / "results.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    json.dump(merged, open(out, "w"), indent=1)
    print("collected:", list(merged))


if __name__ == "__main__":
    main()
