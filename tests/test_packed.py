"""Packed sketch storage, the v3 split rule, the 345-class set and the wide model."""
import pickle
from pathlib import Path

import numpy as np
import pytest
import torch

from src.classsets import CLASS_SETS
from src.data import preprocess
from src.data.packed import PackedSketches, is_packed, load_labels

RAW = Path(__file__).resolve().parents[1] / "data" / "raw"


def sketches(n=40, seed=0):
    rng = np.random.default_rng(seed)
    out = []
    for _ in range(n):
        pts = rng.integers(0, 256, size=(int(rng.integers(4, 60)), 3)).astype(np.float32)
        pts[:, 2] = 0
        pts[-1, 2] = 1
        out.append(pts)
    return out


# ---------------------------------------------------------------- the packed container

def test_it_behaves_like_a_list_of_float_arrays():
    src = sketches()
    p = PackedSketches.from_arrays(src)
    assert len(p) == 40 and all(np.array_equal(p[i], src[i]) for i in range(40))
    assert p[0].dtype == np.float32 and np.array_equal(p[-1], src[-1])
    assert all(np.array_equal(a, b) for a, b in zip(p, src))
    with pytest.raises(IndexError):
        p[40]


def test_it_is_three_bytes_per_point():
    src = sketches()
    assert PackedSketches.from_arrays(src).points.nbytes == 3 * sum(len(s) for s in src)


def test_it_survives_pickling_in_memory_and_reopens_files_instead_of_copying(tmp_path):
    src = sketches()
    p = PackedSketches.from_arrays(src)
    q = pickle.loads(pickle.dumps(p))
    assert all(np.array_equal(q[i], src[i]) for i in range(40))
    p.save(tmp_path, "train", np.arange(40))
    on_disk = PackedSketches.load(tmp_path, "train")
    assert isinstance(on_disk.points, np.memmap) and is_packed(tmp_path)
    blob = pickle.dumps(on_disk)
    assert len(blob) < 1000                                                           # only a path travels to a DataLoader worker
    again = pickle.loads(blob)
    assert all(np.array_equal(again[i], src[i]) for i in range(40)) and list(load_labels(tmp_path, "train")) == list(range(40))


def test_extending_repeats_extra_drawings_after_the_originals():
    a, extra = sketches(10, 1), sketches(3, 2)
    p = PackedSketches.from_arrays(a).extended(extra, 4)
    assert len(p) == 10 + 12 and np.array_equal(p[9], a[9]) and np.array_equal(p[10], extra[0]) and np.array_equal(p[21], extra[2])


# ---------------------------------------------------------------- the split rule

def test_the_split_rule_keeps_the_hundred_class_models_test_drawings_unseen():
    idx = preprocess.packed_indices(30_000, 24_000)
    assert len(idx["train"]) == 24_000 and idx["test"] == list(range(6300, 6600)) and idx["val"] == list(range(6000, 6100))
    assert not set(idx["train"]) & (set(idx["test"]) | set(idx["val"]))                 # no drawing is both trained on and held out
    assert max(i for i in idx["train"] if i < 6000) < 6000 and 6000 not in idx["train"]
    assert not set(idx["test"]) & set(range(6000))                                      # v1 and v2 trained on the first 6000 only


def test_a_class_with_few_drawings_gives_up_training_data_before_test_data():
    idx = preprocess.packed_indices(7_000, 24_000)
    assert len(idx["test"]) == 300 and len(idx["val"]) == 100 and len(idx["train"]) == 6000 + 200 + 400
    assert preprocess.packed_indices(6_200, 24_000)["test"] == []                        # too short to hold anything out: the warning case


@pytest.mark.skipif(not (RAW / "cat.ndjson").exists(), reason="needs the downloaded QuickDraw files")
def test_preprocessing_real_quickdraw_lines_into_a_packed_folder(tmp_path, monkeypatch):
    raw = tmp_path / "raw"
    raw.mkdir()
    with open(RAW / "cat.ndjson", encoding="utf-8") as f:
        (raw / "cat.ndjson").write_text("".join(next(f) for _ in range(12000)), encoding="utf-8")
    monkeypatch.setattr(preprocess, "RAW_DIR", raw)
    monkeypatch.setattr(preprocess, "CLASSES", ["cat"])
    monkeypatch.setattr(preprocess, "DATA_DIR", tmp_path / "out")
    monkeypatch.setattr(preprocess.mp, "Pool", lambda n: __import__("multiprocessing.dummy", fromlist=["Pool"]).Pool(1))      # same code, no subprocess
    preprocess.main_packed(n_train=1000, processes=1)
    root = tmp_path / "out" / "packed"
    train, test = PackedSketches.load(root, "train"), PackedSketches.load(root, "test")
    assert len(train) == 1000 and len(test) == 300 and len(PackedSketches.load(root, "val")) == 100
    assert train[0].shape[1] == 3 and train[0][-1, 2] == 1.0 and 0 <= train[0][:, :2].min() and train[0][:, :2].max() <= 255
    usable = preprocess.read_usable("cat", 6600)
    assert np.array_equal(test[0], np.clip(np.rint(usable[6300]), 0, 255))               # the first test drawing is exactly drawing 6300 of the file
    assert not any(np.array_equal(train[k], test[0]) for k in range(len(train)))         # and was not trained on

    # a set too big for memory is streamed fraction by fraction and gives the same tensors as the resident form
    from src.data import dataset
    monkeypatch.setattr(dataset, "DATA_DIR", tmp_path / "out")
    resident = dataset.eval_set("val", fracs=(0.3,))
    monkeypatch.setattr(dataset, "MAX_RESIDENT_BYTES", 1)
    stream = dataset.eval_set("val", fracs=(0.3,))
    assert isinstance(stream, dataset.EvalStream)
    (frac, tensors), = stream.items()
    assert frac == 0.3 and all(torch.equal(tensors[k], resident[0.3][k]) for k in ("img", "seq", "len", "y"))


# ---------------------------------------------------------------- classes and models

def test_the_345_class_set_is_every_quickdraw_category_and_prefix_stable():
    v1, v2, v3 = (CLASS_SETS[k] for k in ("v1", "v2", "v3"))
    assert (len(v1), len(v2), len(v3)) == (30, 100, 345) and len(set(v3)) == 345
    assert v2[:30] == v1 and v3[:100] == v2                                             # older models stay comparable on the classes they share


def test_the_wide_model_has_the_same_interface_and_more_capacity():
    from src.models.nets import build

    base, wide = build("fusion_ghost"), build("fusion_ghost_xl")
    x = (torch.rand(2, 1, 64, 64), torch.rand(2, 128, 5), torch.tensor([20, 70]))
    for net in (base, wide):
        logits, recon = net.eval()(*x)
        assert logits.shape[0] == 2 and recon.shape == (2, 1, 64, 64)
    assert logits.shape == wide(*x)[0].shape
    count = lambda m: sum(p.numel() for p in m.parameters())               # noqa: E731
    assert count(wide) > 1.7 * count(base)


@pytest.mark.skipif(not Path("runs/fusion_ghost/best.pt").exists(), reason="needs the trained v1 checkpoint")
def test_widening_the_code_did_not_change_the_original_models_layout():
    from src.models.nets import build

    state = torch.load("runs/fusion_ghost/best.pt", map_location="cpu")
    build("fusion_ghost").load_state_dict(state)                               # strict: same names and shapes as when v1 was trained
