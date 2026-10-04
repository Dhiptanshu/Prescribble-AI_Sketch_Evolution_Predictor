"""Server-side model inference for verified scores.

Uses the SAME stroke pipeline code as training (src/data/partial.py) and the same ONNX file the browser runs, so a score the server
computes is the score the model really gives. The browser's own preview can differ by a hair (its canvas rasteriser is a close match,
not an identical one), which is why only the server's number counts.
"""
import json
import sys
import threading
from pathlib import Path

import numpy as np
import onnxruntime as ort
from fastapi import Request

from app.classes import models_dir
from app.errors import ApiError
from app.services.daily import challenge_classes
from app.services.registry import active_version
from app.services.scoring import FRACTIONS, Step

def root_candidates(here: Path) -> tuple[Path, ...]:
    """Where the training-pipeline package (`src`) may live: the repository root when running from a checkout, /app inside the Docker image.
    (From apps/api/app/inference.py the root is four folders up; inside the image the file is /app/app/inference.py, which has no fourth parent.)"""
    parents = here.resolve().parents
    return tuple(p for p in ((parents[3] if len(parents) > 3 else None), Path("/app")) if p is not None)


_ROOT_CANDIDATES = root_candidates(Path(__file__))


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
    def __init__(self, models_dir: Path, version: str, ml_root: Path | None = None, threads: int = 1, concurrency: int = 4):
        """`threads`: ONNX Runtime threads per prediction. One is right for a server: many requests run at once, and a thread per CPU core for EACH of them
        made 16 simultaneous requests fight over the processor (tail latencies of seconds). `concurrency`: how many drawings are scored at the same moment;
        the rest wait their turn, which keeps the server's event loop (WebSocket keep-alives, health checks) responsive during a classroom burst."""
        folder = models_dir / version
        self._slots = threading.BoundedSemaphore(max(1, concurrency))
        self.version = version
        meta = json.loads((folder / "meta.json").read_text(encoding="utf-8"))
        self.classes: list[str] = meta["classes"]
        self.challenge_classes: list[str] = challenge_classes(meta)       # classes fair to set as a daily word or a round word
        self._p = _load_pipeline(ml_root)
        options = ort.SessionOptions()
        options.intra_op_num_threads, options.inter_op_num_threads = max(1, threads), 1
        self._session = ort.InferenceSession(str(folder / "sketch.onnx"), sess_options=options, providers=["CPUExecutionProvider"])

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

    def predict(self, strokes, top_k: int = 5) -> list[tuple[str, float]]:
        """The model's ranked guesses for a drawing as it stands: [(label, probability), ...], best first."""
        with self._slots:
            probs = self.probabilities(_as_array(strokes), 1.0)
        order = np.argsort(-probs)[:top_k]
        return [(self.classes[int(i)], float(probs[i])) for i in order]

    def timeline(self, strokes, target: str) -> list[Step]:
        raw = _as_array(strokes)
        target_idx = self.classes.index(target)
        steps = []
        for f in FRACTIONS:
            with self._slots:                          # one slot per model run, so a long timeline cannot hog the processor while others wait
                probs = self.probabilities(raw, f)
            top = int(np.argmax(probs))
            steps.append(Step(f, self.classes[top], float(probs[top]), float(probs[target_idx])))
        return steps          # the last step is the finished drawing, so it also gives the final guess


def get_scorer(request: Request, version: str | None = None) -> Scorer:
    """The scorer for `version` (default: the live version), loaded on first use and then shared by every request.

    A day's challenge or a classroom round is always scored by the model it started with, even if a newer version goes live meanwhile.
    """
    state = request.app.state
    settings = state.settings
    if version is None:
        if state.scorer is None:
            with state.scorer_lock:
                if state.scorer is None:
                    state.scorer = _load(request, active_version(settings))
        return state.scorer
    if state.scorer is not None and state.scorer.version == version:
        return state.scorer
    with state.scorer_lock:
        if version not in state.scorers:
            state.scorers[version] = _load(request, version)
        return state.scorers[version]


def _load(request: Request, version: str) -> Scorer:
    settings = request.app.state.settings
    folder = models_dir(settings)
    if folder is None or not (folder / version / "sketch.onnx").is_file():
        raise ApiError(503, "model_unavailable", "The scoring model is not available on this server.")
    return Scorer(folder, version, settings.ml_root, settings.ort_threads, settings.scoring_concurrency)


def reload_active(request: Request) -> str:
    """Forget the cached live scorer so the next request loads whatever the registry now says (after a promotion)."""
    state = request.app.state
    with state.scorer_lock:
        state.scorer = None
    return active_version(state.settings)
