"""Geometry checks for the partial-sketch pipeline (run: python -m pytest tests -q)."""
import numpy as np

from src.data.partial import cut_prefix, ink_length, render, to_seq


def line_sketch():
    # two strokes: horizontal 100 px, then vertical 100 px -> 200 px of ink
    return np.array([[10, 10, 0], [110, 10, 1], [110, 20, 0], [110, 120, 1]], np.float32)


def test_cut_respects_ink_fraction():
    pts = line_sketch()
    for f in (0.1, 0.25, 0.5, 0.9):
        assert abs(ink_length(cut_prefix(pts, f)) - f * ink_length(pts)) < 1e-3


def test_full_fraction_returns_everything():
    pts = line_sketch()
    assert len(cut_prefix(pts, 1.0)) == len(pts)


def test_cut_can_stop_mid_stroke():
    part = cut_prefix(line_sketch(), 0.25)   # 50 px into the first 100 px stroke
    assert np.allclose(part[-1, :2], [60, 10])


def test_render_and_seq_shapes():
    part = cut_prefix(line_sketch(), 0.5)
    img = render(part)
    seq, n = to_seq(part)
    assert img.shape == (64, 64) and img.max() <= 1.0 and img.sum() > 0
    assert seq.shape == (128, 5) and n == len(part) and seq[0, 4] == 1.0
