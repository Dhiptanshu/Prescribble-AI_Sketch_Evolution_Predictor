"""Tests for the syllabus experiments: the maths that must be right (metrics, box geometry, ELBO) and the shapes that must line up."""
import numpy as np
import pytest
import torch

from src.syllabus.detection import metrics
from src.syllabus.detection.scenes import MAX_OVERLAP, SIZE, _overlap, make_scene
from src.syllabus.detection.yolo_lite import GRID, STRIDE, YoloLite, build_targets, decode_boxes, giou, predict, yolo_loss


# ---------------------------------------------------------------- metrics (checked against hand-worked cases)

def test_iou_matrix_known_values():
    a = np.array([[0, 0, 10, 10]], float)
    b = np.array([[0, 0, 10, 10], [5, 0, 15, 10], [20, 20, 30, 30]], float)
    assert np.allclose(metrics.iou_matrix(a, b), [[1.0, 1 / 3, 0.0]])        # half-overlap: 50 / (100 + 100 - 50) = 1/3


def test_average_precision_hand_cases():
    assert metrics.average_precision(np.array([1, 1, 1]), 3) == pytest.approx(1.0)               # perfect
    assert metrics.average_precision(np.array([0, 0]), 2) == 0.0                                  # nothing found
    assert metrics.average_precision(np.array([1, 0, 1]), 2) == pytest.approx(1 * 0.5 + (2 / 3) * 0.5)   # P=1 to R=.5, then 2/3 to R=1
    assert metrics.average_precision(np.array([1, 0]), 2) == pytest.approx(0.5)                   # half the objects missed
    assert np.isnan(metrics.average_precision(np.array([1]), 0))                                  # no ground truth: undefined


def test_a_perfect_detector_scores_one_and_a_wrong_class_scores_zero():
    gts = [np.array([[3, 10, 10, 40, 40]], float), np.array([[7, 50, 50, 90, 90], [1, 0, 0, 20, 20]], float)]
    perfect = [np.array([[3, .9, 10, 10, 40, 40]], float), np.array([[7, .8, 50, 50, 90, 90], [1, .7, 0, 0, 20, 20]], float)]
    r = metrics.evaluate(perfect, gts)
    assert r["map50"] == pytest.approx(1.0) and r["map50_95"] == pytest.approx(1.0)
    wrong = [np.array([[4, .9, 10, 10, 40, 40]], float), np.zeros((0, 6))]
    assert metrics.evaluate(wrong, gts)["map50"] == 0.0


def test_duplicate_detections_are_false_positives_and_localisation_sets_the_strict_score():
    gt = [np.array([[0, 0, 0, 100, 100]], float)]
    dup = [np.array([[0, .9, 0, 0, 100, 100], [0, .8, 0, 0, 100, 100]], float)]
    assert metrics.class_ap(dup, gt, 0, 0.5) == pytest.approx(1.0)               # second box is a FP after recall is already 1: AP stays 1
    loose = [np.array([[0, .9, 0, 0, 100, 70]], float)]                          # IoU 0.7
    assert metrics.class_ap(loose, gt, 0, 0.5) == 1.0 and metrics.class_ap(loose, gt, 0, 0.75) == 0.0
    assert 0 < metrics.evaluate(loose, gt)["map50_95"] < 1


def test_a_high_scoring_false_positive_lowers_precision():
    gt = [np.array([[0, 0, 0, 10, 10]], float)]
    fp_first = [np.array([[0, .9, 50, 50, 60, 60], [0, .5, 0, 0, 10, 10]], float)]
    assert metrics.class_ap(fp_first, gt, 0, 0.5) == pytest.approx(0.5)


# ---------------------------------------------------------------- scenes

@pytest.fixture(scope="module")
def digits():
    rng = np.random.default_rng(0)
    d = np.zeros((20, 28, 28), np.uint8)
    for k in range(20):                                       # synthetic stand-in strokes: only the placement geometry is under test
        r0, c0 = rng.integers(4, 10), rng.integers(4, 10)
        d[k, r0:r0 + 12, c0:c0 + 5] = 255
    return d, np.arange(20) % 10


def test_scene_boxes_are_tight_inside_the_frame_and_nearly_disjoint(digits):
    d, y = digits
    rng = np.random.default_rng(1)
    for _ in range(30):
        img, boxes = make_scene(rng, d, y)
        assert img.shape == (SIZE, SIZE) and img.dtype == np.uint8 and 1 <= len(boxes) <= 4
        for c, x1, y1, x2, y2 in boxes:
            assert 0 <= x1 < x2 <= SIZE and 0 <= y1 < y2 <= SIZE
            crop = img[int(y1):int(y2), int(x1):int(x2)]
            assert crop.max() > 30                                              # ink inside the box
            ring = np.pad(img, 1)[int(y1):int(y2) + 2, int(x1):int(x2) + 2].astype(int)
            assert ring.sum() >= crop.sum()
        for i in range(len(boxes)):
            for j in range(i + 1, len(boxes)):
                assert _overlap(boxes[i, 1:], boxes[j, 1:]) <= MAX_OVERLAP + 1e-9


def test_scene_generation_is_deterministic(digits):
    d, y = digits
    a = make_scene(np.random.default_rng(5), d, y)
    b = make_scene(np.random.default_rng(5), d, y)
    assert np.array_equal(a[0], b[0]) and np.array_equal(a[1], b[1])


# ---------------------------------------------------------------- the from-scratch detector

def test_giou_values():
    a = torch.tensor([[0., 0, 10, 10]])
    assert giou(a, a).item() == pytest.approx(1.0)
    assert giou(a, torch.tensor([[20., 0, 30, 10]])).item() < 0                     # disjoint boxes: negative, but with a gradient
    assert giou(a, torch.tensor([[5., 0, 15, 10]])).item() == pytest.approx(1 / 3)       # touching hull equals the union: GIoU = IoU
    near, far = giou(a, torch.tensor([[12., 0, 22, 10]])), giou(a, torch.tensor([[30., 0, 40, 10]]))
    assert near > far                                                               # closer is better even with zero overlap


def test_targets_land_in_the_cell_of_the_box_centre_and_the_larger_box_wins():
    boxes = [np.array([[4, 10, 10, 26, 26], [9, 16, 16, 22, 22], [2, 100, 40, 120, 60]], np.float32)]    # first two share cell (2, 2)
    obj, tbox, tcls = build_targets(boxes, "cpu")
    assert obj.sum() == 2 and obj[0, 2, 2] == 1 and tcls[0, 2, 2] == 4                # the larger box (class 4) keeps the shared cell
    assert obj[0, 50 // STRIDE, 110 // STRIDE] == 1 and tcls[0, 50 // STRIDE, 110 // STRIDE] == 2
    assert tuple(tbox[0, 2, 2].tolist()) == (10, 10, 26, 26)


def test_decoded_boxes_have_cell_relative_centres():
    raw = torch.zeros(1, 15, GRID, GRID)                                              # sigmoid(0) = 0.5: centre mid-cell, size half the image
    b = decode_boxes(raw)
    assert b.shape == (1, GRID, GRID, 4)
    cx = (b[0, 3, 5, 0] + b[0, 3, 5, 2]) / 2
    assert cx.item() == pytest.approx((5 + 0.5) * STRIDE) and (b[0, 3, 5, 2] - b[0, 3, 5, 0]).item() == pytest.approx(SIZE / 2)


def test_the_detector_can_overfit_a_tiny_set_and_then_detects_it():
    torch.manual_seed(0)
    imgs = torch.zeros(2, 1, SIZE, SIZE)
    imgs[0, 0, 20:60, 30:70] = 1
    imgs[1, 0, 70:110, 80:120] = 1
    gt = [np.array([[3, 30, 20, 70, 60]], np.float32), np.array([[7, 80, 70, 120, 110]], np.float32)]
    obj, tbox, tcls = build_targets(gt, "cpu")
    model = YoloLite()
    opt = torch.optim.Adam(model.parameters(), 3e-3)
    first = None
    for step in range(250):
        model.train()
        loss, _ = yolo_loss(model(imgs), obj, tbox, tcls)
        first = first or loss.item()
        opt.zero_grad()
        loss.backward()
        opt.step()
    assert loss.item() < first * 0.2
    preds = predict(model, imgs, conf=0.3)
    assert int(preds[0][0, 0]) == 3 and int(preds[1][0, 0]) == 7
    assert metrics.evaluate(preds, gt)["map50"] > 0.5


# ---------------------------------------------------------------- generative models and classifier

def test_kl_is_zero_for_the_prior_and_positive_otherwise():
    from src.syllabus.vae import loss_terms

    logits, x = torch.zeros(4, 1, 28, 28), torch.zeros(4, 1, 28, 28)
    _, kl0 = loss_terms(logits, x, torch.zeros(4, 3), torch.zeros(4, 3))
    _, kl1 = loss_terms(logits, x, torch.ones(4, 3), torch.zeros(4, 3))
    assert kl0.item() == pytest.approx(0.0, abs=1e-6)
    assert kl1.item() == pytest.approx(0.5 * 3)                                      # 0.5 * mu^2 per dimension


def test_model_shapes_line_up():
    from src.syllabus.ae import ConvAE
    from src.syllabus.digit_cnn import DigitCNN, random_affine
    from src.syllabus.gan import ZDIM, Discriminator, Generator
    from src.syllabus.vae import ConvVAE

    x = torch.rand(5, 1, 28, 28)
    assert ConvAE(8)(x)[0].shape == x.shape and ConvAE(8)(x)[1].shape == (5, 8)
    out, mu, logvar = ConvVAE(2)(x)
    assert out.shape == x.shape and mu.shape == logvar.shape == (5, 2)
    assert DigitCNN()(x).shape == (5, 10)
    g = Generator().eval()(torch.randn(3, ZDIM))
    assert g.shape == (3, 1, 28, 28) and g.min() >= -1 and g.max() <= 1
    assert Discriminator()(g).shape == (3,)
    assert random_affine(x, rot=0, shift=0, scale=0).sub(x).abs().max() < 1e-4        # zero-strength augmentation is the identity
