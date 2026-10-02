"""Partial-sketch utilities: cut a drawing at X% of its ink, rasterize it, build the stroke sequence.

A sketch is a float32 array of shape (N, 3): columns x, y, end_of_stroke (1.0 on the last point of a stroke).
All coordinates are in the fixed 0..255 QuickDraw frame. The prefix is NOT re-normalised, because a live
user has no idea what the final bounding box will be.
"""
import cv2
import numpy as np

from src.common import FRAME, IMG, MAX_PTS, SEQ_FEATS, THICKNESS


def ink_length(pts: np.ndarray) -> float:
    seg = np.linalg.norm(np.diff(pts[:, :2], axis=0), axis=1) * (pts[:-1, 2] == 0)
    return float(seg.sum())


def cut_prefix(pts: np.ndarray, frac: float) -> np.ndarray:
    """Keep the first `frac` of the total ink length (may stop mid-stroke)."""
    if frac >= 1.0 or len(pts) < 2:
        return pts
    seg = np.linalg.norm(np.diff(pts[:, :2], axis=0), axis=1) * (pts[:-1, 2] == 0)
    cum = np.cumsum(seg)
    if cum[-1] <= 0:
        return pts[:1]
    target = frac * cum[-1]
    i = int(np.searchsorted(cum, target))          # segment i (pts[i] -> pts[i+1]) contains the cut
    i = min(i, len(seg) - 1)
    before = cum[i - 1] if i > 0 else 0.0
    t = 0.0 if seg[i] == 0 else (target - before) / seg[i]
    out = pts[: i + 1].copy()
    cut = pts[i, :2] + t * (pts[i + 1, :2] - pts[i, :2])
    return np.vstack([out, np.array([[cut[0], cut[1], 0.0]], dtype=np.float32)])


def split_strokes(pts: np.ndarray):
    ends = np.flatnonzero(pts[:, 2] > 0.5)
    start = 0
    for e in ends:
        yield pts[start : e + 1, :2]
        start = e + 1
    if start < len(pts):
        yield pts[start:, :2]


def render(pts: np.ndarray, size: int = IMG, thickness: int = THICKNESS) -> np.ndarray:
    """Rasterize to a (size, size) float32 image in [0,1], white ink on black."""
    img = np.zeros((size, size), np.uint8)
    scale = (size - 1) / FRAME
    shift = 4
    mul = 1 << shift
    for s in split_strokes(pts):
        p = np.round(s * scale * mul).astype(np.int32)
        if len(p) == 1:
            cv2.circle(img, (int(p[0, 0] // mul), int(p[0, 1] // mul)), max(thickness // 2, 1), 255, -1)
        else:
            cv2.polylines(img, [p.reshape(-1, 1, 2)], False, 255, thickness, cv2.LINE_AA, shift)
    return img.astype(np.float32) / 255.0


def to_seq(pts: np.ndarray, maxlen: int = MAX_PTS):
    """Stroke sequence features (maxlen, 5): x, y, dx, dy, new_stroke. Returns (features, length)."""
    n = len(pts)
    if n > maxlen:  # uniform subsample, always keep the last point
        idx = np.unique(np.linspace(0, n - 1, maxlen).round().astype(int))
        pts = pts[idx]
        n = len(pts)
    xy = pts[:, :2] / FRAME
    d = np.zeros_like(xy)
    d[1:] = (xy[1:] - xy[:-1]) * 8.0
    new = np.zeros(n, np.float32)
    new[0] = 1.0
    new[1:] = pts[:-1, 2]
    d[new > 0.5] = 0.0
    out = np.zeros((maxlen, SEQ_FEATS), np.float32)
    out[:n] = np.concatenate([xy, d, new[:, None]], axis=1)
    return out, n


def rdp(points: np.ndarray, eps: float = 2.0) -> np.ndarray:
    """Ramer-Douglas-Peucker, used to make live drawings look like QuickDraw's simplified data."""
    if len(points) < 3:
        return points
    a, b = points[0], points[-1]
    ab = b - a
    norm = np.linalg.norm(ab)
    if norm == 0:
        d = np.linalg.norm(points - a, axis=1)
    else:
        d = np.abs(ab[0] * (points[:, 1] - a[1]) - ab[1] * (points[:, 0] - a[0])) / norm
    i = int(np.argmax(d))
    if d[i] > eps:
        left = rdp(points[: i + 1], eps)
        right = rdp(points[i:], eps)
        return np.vstack([left[:-1], right])
    return np.vstack([a, b])


def augment(pts: np.ndarray, rng: np.random.Generator) -> np.ndarray:
    """Whole-drawing augmentation applied BEFORE cutting the prefix."""
    xy = pts[:, :2].copy() - 127.5
    if rng.random() < 0.5:
        xy[:, 0] *= -1
    ang = np.deg2rad(rng.uniform(-12, 12))
    c, s = np.cos(ang), np.sin(ang)
    xy = xy @ np.array([[c, -s], [s, c]], dtype=np.float32).T
    xy *= rng.uniform(0.7, 1.1, size=2) if rng.random() < 0.3 else rng.uniform(0.7, 1.1)
    xy += rng.uniform(-14, 14, size=2)
    xy += rng.normal(0, 0.8, size=xy.shape)
    out = pts.copy()
    out[:, :2] = np.clip(xy + 127.5, 0, FRAME)
    return out
