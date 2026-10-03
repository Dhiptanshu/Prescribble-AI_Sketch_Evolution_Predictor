"""Training must see new samples every epoch. (A bug once made every epoch replay the same ones, capping every model we trained.)"""
import numpy as np
import torch
from torch.utils.data import DataLoader

from src.data.dataset import EpochSampler, PartialSketchTrain


def sketches(n=200, seed=0):
    rng = np.random.default_rng(seed)
    out = []
    for _ in range(n):
        pts = rng.integers(10, 245, size=(int(rng.integers(20, 60)), 3)).astype(np.float32)
        pts[:, 2] = 0
        pts[[9, 19, -1], 2] = 1                                  # a few strokes
        out.append(pts)
    return out, rng.integers(0, 5, size=n)


def epoch_images(loader, sampler, epoch):
    sampler.set_epoch(epoch)
    return torch.cat([b["img"] for b in loader])


def test_each_epoch_gets_different_samples_and_a_given_epoch_is_reproducible():
    sk, lb = sketches()
    sampler = EpochSampler(64)
    loader = DataLoader(PartialSketchTrain(sk, lb, 64), batch_size=16, sampler=sampler, num_workers=0)
    e0, e1, e0_again = (epoch_images(loader, sampler, k) for k in (0, 1, 0))
    assert e0.shape == e1.shape == (64, 1, 64, 64)
    assert not torch.equal(e0, e1)                                                       # epoch 1 is not a replay of epoch 0
    assert (e0 != e1).flatten(1).any(1).float().mean() > 0.95                            # and almost every single sample differs
    assert torch.equal(e0, e0_again)                                                     # while one epoch is exactly reproducible


def test_the_sampler_counts_ids_up_across_epochs():
    s = EpochSampler(5)
    assert list(s) == [0, 1, 2, 3, 4] and len(s) == 5
    s.set_epoch(3)
    assert list(s) == [15, 16, 17, 18, 19]


def test_samples_do_not_depend_on_the_worker_processes_seed():
    sk, lb = sketches()
    ds = PartialSketchTrain(sk, lb, 10)
    torch.manual_seed(1)
    a = ds[7]["img"]
    torch.manual_seed(999)
    assert torch.equal(a, ds[7]["img"])                                                  # the id alone decides the sample
