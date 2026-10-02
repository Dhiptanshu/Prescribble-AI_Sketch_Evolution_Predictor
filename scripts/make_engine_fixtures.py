"""Golden fixtures for the TypeScript engine, produced by the canonical Python pipeline (real test sketches).

python scripts/make_engine_fixtures.py
"""
import json
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.data.dataset import load_splits  # noqa: E402
from src.data.partial import cut_prefix, rdp, split_strokes, to_seq  # noqa: E402


def main():
    sk, lb = load_splits()["test"]
    cases = []
    for i in range(0, len(sk), 1500)[:6]:
        full = [s.tolist() for s in split_strokes(sk[i])]
        for frac in (0.2, 0.5, 1.0):
            part = cut_prefix(sk[i], frac)
            seq, n = to_seq(part)
            cases.append({"full": full, "frac": frac, "cut": [s.tolist() for s in split_strokes(part)],
                          "seq": seq.flatten().tolist(), "length": int(n)})
    rdp_cases = []
    for i in range(0, len(sk), 4000)[:3]:
        stroke = np.array(next(split_strokes(sk[i])), dtype=np.float64)
        dense = np.linspace(stroke[0], stroke[-1], 40) + np.sin(np.arange(40))[:, None]      # a noisy dense stroke
        rdp_cases.append({"input": dense.tolist(), "expected": rdp(dense, 2.0).tolist()})
    out = ROOT / "packages" / "engine" / "tests" / "fixtures" / "golden.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    json.dump({"cases": cases, "rdp": rdp_cases}, open(out, "w"))
    print(f"wrote {out} ({len(cases)} pipeline cases, {len(rdp_cases)} rdp cases)")


if __name__ == "__main__":
    main()
