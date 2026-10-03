"""Compose detection scenes from real MNIST digits and export them for YOLOv8.

A scene is a (128, 128) uint8 image and an (n, 5) float array of boxes: class, x1, y1, x2, y2 in pixels (the tight box of the pasted ink).
"""
from pathlib import Path

import cv2
import numpy as np

from src.common import PROC_DIR
from src.syllabus.common import load_mnist

SIZE = 128
MIN_DIGIT, MAX_DIGIT = 28, 56          # pasted digit size in pixels (MNIST digits are 28)
MAX_OBJECTS = 4
MAX_OVERLAP = 0.15                     # largest allowed intersection / smaller box, so boxes stay separable
INK = 0.12                             # pixel level that counts as ink when measuring the box


def _tight_box(digit: np.ndarray) -> tuple[int, int, int, int] | None:
    ys, xs = np.nonzero(digit > INK)
    return None if len(xs) == 0 else (int(xs.min()), int(ys.min()), int(xs.max()) + 1, int(ys.max()) + 1)


def _overlap(a, b) -> float:
    iw, ih = min(a[2], b[2]) - max(a[0], b[0]), min(a[3], b[3]) - max(a[1], b[1])
    if iw <= 0 or ih <= 0:
        return 0.0
    return iw * ih / min((a[2] - a[0]) * (a[3] - a[1]), (b[2] - b[0]) * (b[3] - b[1]))


def make_scene(rng: np.random.Generator, digits: np.ndarray, labels: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """One scene. `digits` is (N, 28, 28) uint8. Placement is retried; an object that cannot be placed is skipped (so a scene may hold fewer)."""
    canvas = np.zeros((SIZE, SIZE), np.float32)
    boxes: list[list[float]] = []
    for _ in range(int(rng.integers(1, MAX_OBJECTS + 1))):
        for _try in range(30):
            k = int(rng.integers(len(digits)))
            side = int(rng.integers(MIN_DIGIT, MAX_DIGIT + 1))
            d = cv2.resize(digits[k].astype(np.float32) / 255, (side, side), interpolation=cv2.INTER_LINEAR)
            tb = _tight_box(d)
            if tb is None:
                continue
            ox, oy = int(rng.integers(0, SIZE - side + 1)), int(rng.integers(0, SIZE - side + 1))
            box = (ox + tb[0], oy + tb[1], ox + tb[2], oy + tb[3])
            if any(_overlap(box, b[1:]) > MAX_OVERLAP for b in boxes):
                continue
            canvas[oy:oy + side, ox:ox + side] = np.maximum(canvas[oy:oy + side, ox:ox + side], d)
            boxes.append([int(labels[k]), *box])
            break
    return (canvas * 255).round().astype(np.uint8), np.asarray(boxes, np.float32).reshape(-1, 5)


def build_scenes(n: int, split: str, seed: int = 0) -> tuple[np.ndarray, list[np.ndarray]]:
    """`split` is 'train' (scenes from MNIST training digits) or 'val' (from MNIST test digits)."""
    x, y = load_mnist(split == "train")
    digits, labels = (x[:, 0] * 255).round().byte().numpy(), y.numpy()
    rng = np.random.default_rng((seed, 0 if split == "train" else 1))
    imgs, boxes = [], []
    for _ in range(n):
        im, bx = make_scene(rng, digits, labels)
        imgs.append(im)
        boxes.append(bx)
    return np.stack(imgs), boxes


def export_yolo_dataset(root: Path, n_train: int, n_val: int, seed: int = 0) -> Path:
    """Write images and YOLO-format labels (class cx cy w h, normalised) plus data.yaml; returns the yaml path."""
    for split, n in (("train", n_train), ("val", n_val)):
        imgs, boxes = build_scenes(n, split, seed)
        (root / "images" / split).mkdir(parents=True, exist_ok=True)
        (root / "labels" / split).mkdir(parents=True, exist_ok=True)
        for i, (im, bx) in enumerate(zip(imgs, boxes)):
            cv2.imwrite(str(root / "images" / split / f"{i:05d}.png"), im)
            lines = [f"{int(c)} {(x1 + x2) / 2 / SIZE:.6f} {(y1 + y2) / 2 / SIZE:.6f} {(x2 - x1) / SIZE:.6f} {(y2 - y1) / SIZE:.6f}" for c, x1, y1, x2, y2 in bx]
            (root / "labels" / split / f"{i:05d}.txt").write_text("\n".join(lines), encoding="utf-8")
    yaml = root / "data.yaml"
    names = "\n".join(f"  {i}: '{i}'" for i in range(10))
    yaml.write_text(f"path: {root.as_posix()}\ntrain: images/train\nval: images/val\nnames:\n{names}\n", encoding="utf-8")
    return yaml


def default_root() -> Path:
    return PROC_DIR / "scenes"
