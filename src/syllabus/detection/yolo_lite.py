"""A single-scale, anchor-free YOLO-style detector written from scratch for the 128x128 digit scenes.

Idea (YOLO): one forward pass divides the image into a grid; each cell predicts "is an object centred here?", where the box is, and what it is.
  input 1x128x128 -> backbone with stride 8 -> a 16x16 grid -> per cell: 1 objectness logit, 2 centre offsets (in the cell), 2 box sizes
  (as a fraction of the image) and 10 class logits.
Training target: each ground-truth box is assigned to the cell holding its centre. Loss = BCE objectness (empty cells down-weighted)
  + (1 - GIoU) box loss and cross-entropy class loss on the assigned cells only.
Decoding: score = objectness * class probability, confidence threshold, then per-class non-maximum suppression.
"""
import numpy as np
import torch
import torch.nn as nn
import torch.nn.functional as F
import torchvision

from src.syllabus.detection.scenes import SIZE

GRID = 16
STRIDE = SIZE // GRID
NC = 10


def cbl(i: int, o: int, s: int = 1) -> nn.Sequential:
    return nn.Sequential(nn.Conv2d(i, o, 3, s, 1, bias=False), nn.BatchNorm2d(o), nn.LeakyReLU(0.1, inplace=True))


class YoloLite(nn.Module):
    """About 0.6 M parameters. Output (B, 5 + NC, GRID, GRID)."""

    def __init__(self):
        super().__init__()
        self.body = nn.Sequential(cbl(1, 16), cbl(16, 32, 2), cbl(32, 32),            # 64
                                  cbl(32, 64, 2), cbl(64, 64),                        # 32
                                  cbl(64, 128, 2), cbl(128, 128), cbl(128, 128))      # 16 (stride 8)
        self.head = nn.Conv2d(128, 5 + NC, 1)

    def forward(self, x):
        return self.head(self.body(x))


def decode_boxes(raw: torch.Tensor) -> torch.Tensor:
    """(B, 5+NC, G, G) raw output -> boxes (B, G, G, 4) as x1,y1,x2,y2 in pixels."""
    b, _, g, _ = raw.shape
    gy, gx = torch.meshgrid(torch.arange(g, device=raw.device), torch.arange(g, device=raw.device), indexing="ij")
    cx = (gx + raw[:, 1].sigmoid()) * STRIDE
    cy = (gy + raw[:, 2].sigmoid()) * STRIDE
    w, h = raw[:, 3].sigmoid() * SIZE, raw[:, 4].sigmoid() * SIZE
    return torch.stack([cx - w / 2, cy - h / 2, cx + w / 2, cy + h / 2], -1)


def giou(a: torch.Tensor, b: torch.Tensor) -> torch.Tensor:
    """Generalised IoU of paired boxes (n,4); in [-1, 1], it still has a gradient when the boxes do not overlap."""
    iw = (torch.min(a[:, 2], b[:, 2]) - torch.max(a[:, 0], b[:, 0])).clamp(min=0)
    ih = (torch.min(a[:, 3], b[:, 3]) - torch.max(a[:, 1], b[:, 1])).clamp(min=0)
    inter = iw * ih
    union = (a[:, 2] - a[:, 0]) * (a[:, 3] - a[:, 1]) + (b[:, 2] - b[:, 0]) * (b[:, 3] - b[:, 1]) - inter
    iou = inter / (union + 1e-9)
    cw = torch.max(a[:, 2], b[:, 2]) - torch.min(a[:, 0], b[:, 0])
    ch = torch.max(a[:, 3], b[:, 3]) - torch.min(a[:, 1], b[:, 1])
    hull = cw * ch + 1e-9
    return iou - (hull - union) / hull


def build_targets(boxes: list[np.ndarray], device) -> tuple[torch.Tensor, torch.Tensor, torch.Tensor]:
    """Per image, assign each box to the cell containing its centre (the larger box wins a shared cell).
    Returns obj (B,G,G) 0/1, target boxes (B,G,G,4) and classes (B,G,G) long."""
    b = len(boxes)
    obj = torch.zeros(b, GRID, GRID)
    tbox = torch.zeros(b, GRID, GRID, 4)
    tcls = torch.zeros(b, GRID, GRID, dtype=torch.long)
    area = torch.zeros(b, GRID, GRID)
    for i, bx in enumerate(boxes):
        for c, x1, y1, x2, y2 in bx:
            gx, gy = min(GRID - 1, int((x1 + x2) / 2 // STRIDE)), min(GRID - 1, int((y1 + y2) / 2 // STRIDE))
            a = float((x2 - x1) * (y2 - y1))
            if a > area[i, gy, gx]:
                area[i, gy, gx], obj[i, gy, gx] = a, 1
                tbox[i, gy, gx] = torch.tensor([float(x1), float(y1), float(x2), float(y2)])
                tcls[i, gy, gx] = int(c)
    return obj.to(device), tbox.to(device), tcls.to(device)


def yolo_loss(raw: torch.Tensor, obj: torch.Tensor, tbox: torch.Tensor, tcls: torch.Tensor, w_noobj: float = 0.5, w_box: float = 5.0):
    """Returns (total, parts dict). Objectness over every cell, box and class only where an object is assigned."""
    obj_logit = raw[:, 0]
    weight = torch.where(obj > 0, torch.ones_like(obj), torch.full_like(obj, w_noobj))
    l_obj = (F.binary_cross_entropy_with_logits(obj_logit, obj, reduction="none") * weight).sum() / obj.size(0)
    pos = obj > 0
    if pos.any():
        pred = decode_boxes(raw)[pos]
        l_box = (1 - giou(pred, tbox[pos])).mean()
        l_cls = F.cross_entropy(raw[:, 5:].permute(0, 2, 3, 1)[pos], tcls[pos])
    else:
        l_box = l_cls = raw.sum() * 0
    total = l_obj + w_box * l_box + l_cls
    return total, {"obj": l_obj.item(), "box": l_box.item(), "cls": l_cls.item()}


@torch.no_grad()
def predict(model: nn.Module, images: torch.Tensor, conf: float = 0.01, iou: float = 0.5, max_det: int = 20) -> list[np.ndarray]:
    """Images (B,1,128,128) float in [0,1] -> per image an (n, 6) array: class, score, x1, y1, x2, y2."""
    model.eval()
    raw = model(images)
    boxes = decode_boxes(raw)                                          # (B,G,G,4)
    cls_p = raw[:, 5:].softmax(1)                                      # (B,NC,G,G)
    scores_all = raw[:, 0].sigmoid().unsqueeze(1) * cls_p              # objectness x class probability, per class
    out = []
    for i in range(len(images)):
        s = scores_all[i].permute(1, 2, 0).reshape(-1, NC)             # (G*G, NC)
        bx = boxes[i].reshape(-1, 4)
        cells, classes = torch.nonzero(s > conf, as_tuple=True)
        if len(cells) == 0:
            out.append(np.zeros((0, 6), np.float32))
            continue
        sc, bb = s[cells, classes], bx[cells]
        keep = torchvision.ops.batched_nms(bb, sc, classes, iou)[:max_det]
        out.append(torch.cat([classes[keep, None].float(), sc[keep, None], bb[keep]], 1).cpu().numpy())
    return out
