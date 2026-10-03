"""Detection metrics written out in full (no library): IoU, VOC-style average precision, mAP@0.5 and mAP@[0.5:0.95].

A prediction is (class, score, x1, y1, x2, y2); ground truth is (class, x1, y1, x2, y2). Per class, predictions are sorted by score and matched
greedily to the best unmatched ground-truth box with IoU above the threshold; AP is the area under the precision-recall curve (all-point
interpolation, as in Pascal VOC 2010+).
"""
import numpy as np


def iou_matrix(a: np.ndarray, b: np.ndarray) -> np.ndarray:
    """IoU of every box in a (n,4) with every box in b (m,4), boxes as x1,y1,x2,y2."""
    if len(a) == 0 or len(b) == 0:
        return np.zeros((len(a), len(b)))
    iw = np.minimum(a[:, None, 2], b[None, :, 2]) - np.maximum(a[:, None, 0], b[None, :, 0])
    ih = np.minimum(a[:, None, 3], b[None, :, 3]) - np.maximum(a[:, None, 1], b[None, :, 1])
    inter = np.clip(iw, 0, None) * np.clip(ih, 0, None)
    area_a = (a[:, 2] - a[:, 0]) * (a[:, 3] - a[:, 1])
    area_b = (b[:, 2] - b[:, 0]) * (b[:, 3] - b[:, 1])
    return inter / (area_a[:, None] + area_b[None, :] - inter + 1e-12)


def average_precision(tp: np.ndarray, n_gt: int) -> float:
    """`tp` are 1/0 flags of predictions already sorted by descending score; n_gt is the number of ground-truth boxes."""
    if n_gt == 0:
        return float("nan")
    if len(tp) == 0:
        return 0.0
    cum_tp = np.cumsum(tp)
    recall = cum_tp / n_gt
    precision = cum_tp / np.arange(1, len(tp) + 1)
    mrec = np.concatenate([[0.0], recall, [1.0]])
    mpre = np.concatenate([[1.0], precision, [0.0]])
    mpre = np.maximum.accumulate(mpre[::-1])[::-1]               # make precision monotonically decreasing
    idx = np.flatnonzero(mrec[1:] != mrec[:-1])
    return float(np.sum((mrec[idx + 1] - mrec[idx]) * mpre[idx + 1]))


def class_ap(preds: list[np.ndarray], gts: list[np.ndarray], cls: int, thr: float) -> float:
    """AP of one class over a set of images (preds[i], gts[i] belong to image i)."""
    records, n_gt = [], 0
    for i, (p, g) in enumerate(zip(preds, gts)):
        n_gt += int((g[:, 0] == cls).sum()) if len(g) else 0
        pc = p[p[:, 0] == cls] if len(p) else p.reshape(0, 6)
        for row in pc:
            records.append((row[1], i, row[2:6]))
    records.sort(key=lambda r: -r[0])
    used = {i: np.zeros(int((g[:, 0] == cls).sum()) if len(g) else 0, bool) for i, g in enumerate(gts)}
    tp = np.zeros(len(records))
    for k, (_, i, box) in enumerate(records):
        g = gts[i][gts[i][:, 0] == cls][:, 1:5] if len(gts[i]) else np.zeros((0, 4))
        if len(g) == 0:
            continue
        ious = iou_matrix(box[None], g)[0]
        ious[used[i]] = -1                                      # each ground-truth box can be claimed once
        j = int(ious.argmax())
        if ious[j] >= thr:
            used[i][j] = True
            tp[k] = 1
    return average_precision(tp, n_gt)


def evaluate(preds: list[np.ndarray], gts: list[np.ndarray], n_classes: int = 10) -> dict:
    """mAP@0.5, mAP@[0.5:0.95] (steps of 0.05) and per-class AP@0.5, averaged over classes that appear in the ground truth."""
    thresholds = np.arange(0.5, 0.96, 0.05)
    ap = np.array([[class_ap(preds, gts, c, t) for t in thresholds] for c in range(n_classes)])      # (class, threshold)
    present = ~np.isnan(ap[:, 0])
    return {"map50": float(np.nanmean(ap[present, 0])), "map50_95": float(np.nanmean(ap[present])),
            "ap50_per_class": [None if np.isnan(v) else float(v) for v in ap[:, 0]]}
