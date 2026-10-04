"""Evaluation metrics, checked against cases worked out by hand."""
import numpy as np
import pytest

from src.eval import metrics


def test_wilson_interval_is_centred_sensible_and_shrinks_with_more_data():
    lo, hi = metrics.wilson(50, 100)
    assert lo < 0.5 < hi and 0.40 < lo < 0.41 and 0.59 < hi < 0.60              # the textbook 95% interval for 50 of 100
    lo2, hi2 = metrics.wilson(500, 1000)
    assert hi2 - lo2 < hi - lo
    assert metrics.wilson(0, 10)[0] == 0.0 and metrics.wilson(10, 10)[1] == 1.0


def test_topk_and_masking():
    probs = np.array([[0.5, 0.3, 0.2], [0.1, 0.2, 0.7]])
    y = np.array([1, 0])
    order = metrics.ranked(probs)
    assert metrics.topk_hits(order, y, 1).tolist() == [False, False]
    assert metrics.topk_hits(order, y, 2).tolist() == [True, False]
    masked = metrics.ranked(probs, np.array([True, True, False]))                # class 2 may not be answered
    assert masked[1, 0] == 1 and metrics.topk_hits(masked, y, 2).tolist() == [True, True]


def test_confusion_and_macro_scores():
    y = np.array([0, 0, 1, 1, 2])
    pred = np.array([0, 1, 1, 1, 0])
    conf = metrics.confusion(pred, y, 3)
    assert conf.tolist() == [[1, 1, 0], [0, 2, 0], [1, 0, 0]]
    s = metrics.macro_prf(conf)
    assert s["recall"] == pytest.approx((0.5 + 1.0 + 0.0) / 3)
    assert s["precision"] == pytest.approx((0.5 + 2 / 3 + 0.0) / 3)
    assert metrics.top_confusions(conf, ["a", "b", "c"], 2)[0][2] == 1


def test_calibration_of_a_perfectly_calibrated_and_an_overconfident_model():
    n = 1000
    rng = np.random.default_rng(0)
    probs = np.tile([0.8, 0.2], (n, 1))
    y = np.where(rng.random(n) < 0.8, 0, 1)                                       # right 80% of the time when it says 80%
    assert metrics.calibration(probs, y)["ece"] < 0.05
    sure = np.tile([0.99, 0.01], (n, 1))
    assert metrics.calibration(sure, y)["ece"] > 0.15                             # says 99%, is right about 80%


def test_nll_and_brier_on_known_values():
    probs = np.array([[0.9, 0.1], [0.5, 0.5]])
    y = np.array([0, 1])
    assert metrics.nll(probs, y) == pytest.approx(-(np.log(0.9) + np.log(0.5)) / 2)
    assert metrics.brier(probs, y) == pytest.approx(((0.01 + 0.01) + (0.25 + 0.25)) / 2)


def test_first_hit_with_and_without_staying_right():
    fracs = np.array([0.2, 0.5, 1.0])
    correct = np.array([[False, True, True], [True, False, True], [False, False, False]])
    assert np.allclose(metrics.first_hit(correct, fracs), [0.5, 0.2, np.nan], equal_nan=True)
    assert np.allclose(metrics.first_hit(correct, fracs, stays=True), [0.5, 1.0, np.nan], equal_nan=True)
