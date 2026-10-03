"""PyTorch datasets. Training: random augmentation + random completion fraction every call.
Evaluation: deterministic fractions, no augmentation, cached tensors."""
import pickle

import numpy as np
import torch
from torch.utils.data import Dataset

from src.common import DATA_DIR, EVAL_FRACS
from src.data.partial import augment, cut_prefix, render, to_seq


def load_splits() -> dict:
    with open(DATA_DIR / "sketches.pkl", "rb") as f:
        return pickle.load(f)


def sample_frac(rng: np.random.Generator) -> float:
    """Emphasise the early regime (15-40%) that the project is about, but see everything."""
    if rng.random() < 0.5:
        return float(rng.uniform(0.12, 0.40))
    return float(rng.uniform(0.10, 1.0))


class PartialSketchTrain(Dataset):
    def __init__(self, sketches, labels, epoch_size: int | None = None, seed: int = 0):
        self.sketches, self.labels = sketches, labels
        self.n = epoch_size or len(sketches)
        self.seed = seed

    def __len__(self):
        return self.n

    def __getitem__(self, i):
        rng = np.random.default_rng((self.seed, i, torch.initial_seed() % (2**31)))
        j = int(rng.integers(len(self.sketches)))
        full = augment(self.sketches[j], rng)
        part = cut_prefix(full, sample_frac(rng))
        seq, n = to_seq(part)
        return {
            "img": torch.from_numpy(render(part))[None],
            "seq": torch.from_numpy(seq),
            "len": torch.tensor(n),
            "target": torch.from_numpy(render(full))[None],
            "y": torch.tensor(int(self.labels[j])),
        }


def _u8(img: np.ndarray) -> np.ndarray:
    return (img * 255).round().astype(np.uint8)


def _eval_one(args):
    pts, frac = args
    part = cut_prefix(pts, frac)
    s, n = to_seq(part)
    return _u8(render(part)), s, n, _u8(render(pts))


def build_eval_tensors(sketches, labels, frac: float, pool=None) -> dict:
    """Images are stored as uint8 (4x smaller); use `as_float` before feeding a model."""
    jobs = [(p, frac) for p in sketches]
    rows = pool.map(_eval_one, jobs, chunksize=256) if pool else [_eval_one(j) for j in jobs]
    imgs, seqs, lens, targets = zip(*rows)
    return {
        "img": torch.from_numpy(np.stack(imgs))[:, None],
        "seq": torch.from_numpy(np.stack(seqs)),
        "len": torch.tensor(lens),
        "target": torch.from_numpy(np.stack(targets))[:, None],
        "y": torch.from_numpy(np.asarray(labels)),
    }


def as_float(d: dict) -> dict:
    """uint8 images -> float32 in [0,1] (apply to a slice, not the whole set)."""
    return {**d, "img": d["img"].float() / 255.0, "target": d["target"].float() / 255.0}


def eval_set(split: str, fracs=EVAL_FRACS) -> dict:
    """{frac: tensors}, cached on disk after the first build (parallel)."""
    import multiprocessing as mp

    cache = DATA_DIR / f"eval_{split}.pt"
    if cache.exists():
        return torch.load(cache, map_location="cpu")
    sk, lb = load_splits()[split]
    with mp.Pool(4) as pool:
        data = {f: build_eval_tensors(sk, lb, f, pool) for f in fracs}
    torch.save(data, cache)
    return data
