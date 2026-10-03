"""Millions of sketches in a few GB: one flat uint8 array of points plus offsets, memory-mapped from disk.

QuickDraw's simplified coordinates are integers in 0..255, so a point (x, y, end-of-stroke flag) takes 3 bytes instead of the 12 of a float32 row.
A PackedSketches behaves like a read-only list of float32 (N, 3) arrays (the training pipeline's format) but holds no Python object per sketch,
so DataLoader workers share the same pages instead of each copying millions of arrays.

Layout of a packed folder: {split}_points.npy (P, 3) uint8, {split}_offsets.npy (n + 1,) int64, {split}_labels.npy (n,) int16.
"""
from pathlib import Path

import numpy as np


class PackedSketches:
    def __init__(self, points: np.ndarray, offsets: np.ndarray, root: Path | None = None, split: str | None = None):
        self.points, self.offsets = points, offsets
        self._root, self._split = root, split              # where it came from, so a pickled copy reopens the files instead of copying them

    def __len__(self) -> int:
        return len(self.offsets) - 1

    def __getitem__(self, i: int) -> np.ndarray:
        n = len(self)
        i = int(i)
        if not -n <= i < n:
            raise IndexError(i)
        i %= n
        return np.asarray(self.points[self.offsets[i]:self.offsets[i + 1]], dtype=np.float32)

    def __iter__(self):
        for i in range(len(self)):
            yield self[i]

    def __getstate__(self):
        if self._root is not None:
            return {"root": self._root, "split": self._split}
        return {"points": np.asarray(self.points), "offsets": np.asarray(self.offsets)}

    def __setstate__(self, state):
        if "root" in state:
            loaded = PackedSketches.load(state["root"], state["split"])
            self.points, self.offsets, self._root, self._split = loaded.points, loaded.offsets, loaded._root, loaded._split
        else:
            self.points, self.offsets, self._root, self._split = state["points"], state["offsets"], None, None

    # ------------------------------------------------------------------ building and storing
    @classmethod
    def from_arrays(cls, sketches) -> "PackedSketches":
        """From any sequence of (N, 3) float arrays with integer-valued coordinates."""
        lengths = np.fromiter((len(s) for s in sketches), np.int64, count=len(sketches))
        points = np.empty((int(lengths.sum()), 3), np.uint8)
        pos = 0
        for s, n in zip(sketches, lengths):
            points[pos:pos + n] = np.clip(np.rint(s), 0, 255)
            pos += n
        return cls(points, np.concatenate([[0], np.cumsum(lengths)]))

    def extended(self, extra, repeats: int = 1) -> "PackedSketches":
        """A new PackedSketches with `extra` (a list of arrays) appended `repeats` times (used to mix user drawings into a training stream)."""
        tail = PackedSketches.from_arrays(list(extra) * repeats)
        points = np.concatenate([np.asarray(self.points), tail.points])
        offsets = np.concatenate([np.asarray(self.offsets), tail.offsets[1:] + int(self.offsets[-1])])
        return PackedSketches(points, offsets)

    def save(self, root: Path, split: str, labels: np.ndarray) -> None:
        root.mkdir(parents=True, exist_ok=True)
        np.save(root / f"{split}_points.npy", np.asarray(self.points))
        np.save(root / f"{split}_offsets.npy", np.asarray(self.offsets))
        np.save(root / f"{split}_labels.npy", labels.astype(np.int16))

    @classmethod
    def load(cls, root: Path, split: str) -> "PackedSketches":
        return cls(np.load(root / f"{split}_points.npy", mmap_mode="r"), np.load(root / f"{split}_offsets.npy"), root, split)


def load_labels(root: Path, split: str) -> np.ndarray:
    return np.load(root / f"{split}_labels.npy").astype(np.int64)


def is_packed(root: Path) -> bool:
    return (root / "train_points.npy").is_file()
