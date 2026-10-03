"""The user-drawing mix and split. Real QuickDraw sketches (models/v1/samples.json) act as the user records so the real code path runs."""
import hashlib
import json
from pathlib import Path

import numpy as np
import pytest

from src.common import CLASSES
from src.flywheel import dataset
from src.flywheel.mix import mix_user_drawings, user_arrays

SAMPLES = json.loads((Path(__file__).resolve().parents[1] / "models" / "v1" / "samples.json").read_text(encoding="utf-8"))


def records(n=90, input_type="mouse", label_override=None):
    out = []
    for i, s in enumerate(SAMPLES[:n]):
        out.append({"uid": hashlib.sha256(f"t:{i}".encode()).hexdigest()[:16], "label": label_override or s["label"], "strokes": s["strokes"],
                    "source": "teach", "input_type": input_type if i % 2 == 0 else "touch"})
    return out


@pytest.fixture
def file(tmp_path):
    p = tmp_path / "user.jsonl"
    p.write_text("\n".join(json.dumps(r) for r in records()), encoding="utf-8")
    return p


def test_the_split_is_stable_and_about_one_in_five():
    recs = records()
    train, held = dataset.split(recs)
    assert len(train) + len(held) == 90 and 8 <= len(held) <= 30
    assert dataset.split(list(reversed(recs)))[1] == list(reversed(held)) or {r["uid"] for r in dataset.split(list(reversed(recs)))[1]} == {r["uid"] for r in held}
    assert not {r["uid"] for r in train} & {r["uid"] for r in held}


def test_user_arrays_only_keep_current_classes_and_can_filter_by_pointer(tmp_path):
    recs = records() + [{**records(1)[0], "uid": "ffffffff" + "0" * 8, "label": "not a class"}]
    p = tmp_path / "u.jsonl"
    p.write_text("\n".join(json.dumps(r) for r in recs), encoding="utf-8")
    xs, ys, xh, yh = user_arrays(p)
    assert len(xs) + len(xh) == 90 and set(np.concatenate([ys, yh])) <= set(range(len(CLASSES)))
    mxs, _, mxh, _ = user_arrays(p, "mouse")
    assert len(mxs) + len(mxh) == 45                                                       # every other record was made with a mouse
    assert xs[0].shape[1] == 3                                                             # the training pipeline's (x, y, end-of-stroke) rows


def test_the_mix_makes_user_drawings_the_requested_share(file):
    qd = [np.zeros((5, 3), np.float32)] * 10_000
    labels = np.zeros(10_000, np.int64)
    xs, ys, _, _ = user_arrays(file)
    for share in (0.1, 0.25, 0.5):
        mixed, mixed_labels = mix_user_drawings(qd, labels, file, share)
        added = len(mixed) - 10_000
        assert len(mixed) == len(mixed_labels) and added % len(xs) == 0                    # whole repetitions of the training split
        assert abs(added / len(mixed) - share) < 0.02


def test_the_held_out_drawings_are_never_mixed_in(file):
    _, _, xh, _ = user_arrays(file)
    mixed, _ = mix_user_drawings([np.zeros((5, 3), np.float32)] * 1000, np.zeros(1000, np.int64), file, 0.3)
    held_ids = {id(a) for a in xh}
    assert not any(id(a) in held_ids for a in mixed)


def test_bad_requests_are_refused(file, tmp_path):
    with pytest.raises(ValueError, match="share"):
        mix_user_drawings([], np.array([]), file, 1.0)
    empty = tmp_path / "e.jsonl"
    empty.write_text(json.dumps({**records(1)[0], "label": "nope"}), encoding="utf-8")
    with pytest.raises(ValueError, match="no user training drawings"):
        mix_user_drawings([np.zeros((5, 3), np.float32)], np.zeros(1, np.int64), empty, 0.2)
