"""Mix the training split of consented user drawings into the QuickDraw training stream.

QuickDraw has hundreds of thousands of sketches and a deployment's users a few hundred, so user drawings are repeated until they make up
`share` of what the model sees (the training pipeline augments and re-cuts every repetition differently, so they are not literal copies).
The held-out fifth of the user drawings (src/flywheel/dataset.py) is never mixed in: it is what the before / after comparison is measured on.
"""
from pathlib import Path

import numpy as np

from src.common import CLASSES
from src.flywheel import dataset


def user_arrays(path: Path, input_type: str | None = None) -> tuple[list[np.ndarray], np.ndarray, list[np.ndarray], np.ndarray]:
    """(train sketches, train label ids, held-out sketches, held-out label ids) for the user drawings whose label is a current class."""
    records = [r for r in dataset.read_jsonl(path) if r["label"] in CLASSES and (input_type is None or r.get("input_type") == input_type)]
    train, held = dataset.split(records)
    index = {c: i for i, c in enumerate(CLASSES)}
    (xs, names), (xh, nh) = dataset.to_arrays(train), dataset.to_arrays(held)
    return xs, np.array([index[n] for n in names], np.int64), xh, np.array([index[n] for n in nh], np.int64)


def mix_user_drawings(sketches: list, labels: np.ndarray, path: Path, share: float, input_type: str | None = None) -> tuple[list, np.ndarray]:
    """QuickDraw (sketches, labels) plus the user training drawings repeated so they are about `share` of the combined stream."""
    if not 0 < share < 1:
        raise ValueError("share must be between 0 and 1")
    xs, ys, _, _ = user_arrays(path, input_type)
    if not len(xs):
        raise ValueError("there are no user training drawings for the current classes in that file")
    reps = max(1, round(share / (1 - share) * len(sketches) / len(xs)))
    return list(sketches) + xs * reps, np.concatenate([labels, np.tile(ys, reps)])
