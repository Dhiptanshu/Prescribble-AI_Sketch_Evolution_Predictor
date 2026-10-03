"""Server-side model inference for verified scores.

Uses the SAME stroke pipeline code as training (src/data/partial.py) and the same ONNX file the browser runs, so a score the server
computes is the score the model really gives. The browser's own preview can differ by a hair (its canvas rasteriser is a close match,
not an identical one), which is why only the server's number counts.
"""
import json
import sys
from pathlib import Path

import numpy as np
import onnxruntime as ort

from app.services.scoring import FRACTIONS, Step

_ROOT_CANDIDATES = (Path(__file__).resolve().parents[3], Path("/app"))


def _load_pipeline(ml_root: Path | None):
    for root in ([ml_root] if ml_root else list(_ROOT_CANDIDATES)):
        if root and (root / "src" / "data" / "partial.py").is_file():
            if str(root) not in sys.path:
                sys.path.insert(0, str(root))
            from src.data import partial          # noqa: PLC0415  (path is set up just above)
            return partial
    raise RuntimeError("training pipeline (src/data/partial.py) not found; set PRESCRIBBLE_ML_ROOT")


def _as_array(strokes) -> np.ndarray:
    """Strokes -> (N, 3) float32 rows of x, y, end-of-stroke flag, the format of the training pipeline."""
    rows = []
    for s in strokes:
        for i, (x, y) in enumerate(s):
            rows.append((x, y, 1.0 if i == len(s) - 1 else 0.0))
    return np.asarray(rows, np.float32)


class Scorer:
    def __init__(self, models_dir: Path, version: str, ml_root: Path | None = None):
        folder = models_dir / version
        self.version = version
        self.classes: list[str] = json.loads((folder / "meta.json").read_text(encoding="utf-8"))["classes"]
        self._p = _load_pipeline(ml_root)
        self._session = ort.InferenceSession(str(folder / "sketch.onnx"), providers=["CPUExecutionProvider"])

    def probabilities(self, raw: np.ndarray, fraction: float) -> np.ndarray:
        """Class probabilities when only `fraction` of the drawing's ink is down: cut, simplify like the browser does, featurise, run."""
        p = self._p
        part = p.cut_prefix(raw, fraction)
        simplified = _as_array([p.rdp(s.astype(np.float64), 2.0) for s in p.split_strokes(part)])
        seq, length = p.to_seq(simplified)
        out = self._session.run(["probs"], {
            "img": p.render(simplified)[None, None].astype(np.float32),
            "seq": seq[None].astype(np.float32),
            "length": np.array([length], dtype=np.int64),
        })
        return out[0][0]

    def timeline(self, strokes, target: str) -> list[Step]:
        raw = _as_array(strokes)
        target_idx = self.classes.index(target)
        steps = []
        for f in FRACTIONS:
            probs = self.probabilities(raw, f)
            top = int(np.argmax(probs))
            steps.append(Step(f, self.classes[top], float(probs[top]), float(probs[target_idx])))
        return steps          # the last step is the finished drawing, so it also gives the final guess
