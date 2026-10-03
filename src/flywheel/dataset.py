"""Read an export of consented user drawings (apps/api: `python -m app.cli export-training`) and split it for retraining and evaluation.

One JSON object per line: {"uid", "label", "strokes", "source", "input_type", "model_version", "created"}. The uid is a one-way hash of the
drawing's id, so the same drawing always lands on the same side of the split and no account identity is in the file. About one drawing in
five is held out: the retraining job never sees it, and the promotion gate and the reports measure on it.
"""
import json
from pathlib import Path

import numpy as np

from src.flywheel.onnx_eval import as_array

HELDOUT_EVERY = 5


def read_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in Path(path).read_text(encoding="utf-8").splitlines() if line.strip()]


def is_heldout(uid: str) -> bool:
    return int(uid[:8], 16) % HELDOUT_EVERY == 0


def split(records: list[dict]) -> tuple[list[dict], list[dict]]:
    """(train, heldout)."""
    train = [r for r in records if not is_heldout(r["uid"])]
    held = [r for r in records if is_heldout(r["uid"])]
    return train, held


def to_arrays(records: list[dict]) -> tuple[list[np.ndarray], list[str]]:
    """Training-pipeline arrays and label names for a list of records."""
    return [as_array(r["strokes"]) for r in records], [r["label"] for r in records]


def by_input_type(records: list[dict]) -> dict[str, list[dict]]:
    out: dict[str, list[dict]] = {}
    for r in records:
        out.setdefault(r.get("input_type") or "unknown", []).append(r)
    return out
