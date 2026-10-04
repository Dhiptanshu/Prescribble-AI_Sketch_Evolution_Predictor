"""Run the registry's promotion comparison between two model versions WITHOUT promoting anything, and save the report.

python scripts/compare_models.py --live v1 --candidate v3 --heldout data/processed/v3/heldout.pkl --out docs/results/gate_v1_to_v3.json
The same code the promotion gate runs (src/flywheel/gate.py): held-out sketches of the classes both models know, both limited to those classes.
"""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.flywheel.gate import compare  # noqa: E402


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--live", required=True)
    ap.add_argument("--candidate", required=True)
    ap.add_argument("--heldout", type=Path, required=True)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--per-class", type=int, default=30)
    ap.add_argument("--tolerance", type=float, default=0.01)
    a = ap.parse_args()
    result = compare(Path(__file__).resolve().parent.parent / "models", a.candidate, a.live, a.heldout, None, a.tolerance, 30, a.per_class)
    a.out.write_text(json.dumps({"candidate": a.candidate, "active_before": a.live, "comparison": result}, indent=2), encoding="utf-8")
    q = result["verdict"]["quickdraw"]
    print(f"{a.live} -> {a.candidate}: {q['n']} sketches, both limited to the shared classes: {q['active_top5']:.4f} vs {q['candidate_top5']:.4f} "
          f"({q['delta']:+.4f}); candidate free to answer with any of its classes: {q['candidate_unmasked_top5']:.4f}; passed={result['passed']}", flush=True)


if __name__ == "__main__":
    main()
