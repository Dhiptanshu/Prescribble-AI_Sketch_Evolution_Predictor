"""Module V: YOLOv8n transfer learning on the digit scenes, with the controlled comparison that shows what transfer buys.

  pretrained  yolov8n.pt (COCO weights) fine-tuned on the scenes
  scratch     the same yolov8n architecture, random initial weights, same data, same epochs

Both are scored with OUR metric (metrics.py) on the same validation scenes as the from-scratch detector (train_scratch.py), plus Ultralytics' own mAP.
python -m src.syllabus.detection.train_yolov8 [--epochs 30] [--train 20000] [--val 2000] [--smoke]
Outputs runs/syllabus/det_yolov8/results.json and report/figures/syllabus_det_yolov8.png
"""
import argparse
import shutil
import time

import numpy as np
import torch

from src.syllabus.common import SYLLABUS_RUNS, device, save_figure, save_results, style
from src.syllabus.detection import metrics
from src.syllabus.detection.scenes import build_scenes, default_root, export_yolo_dataset

# No flips or colour jitter (a flipped digit is a different digit); mosaic off so the data matches the from-scratch detector's.
AUG = dict(fliplr=0.0, flipud=0.0, hsv_h=0.0, hsv_s=0.0, hsv_v=0.0, mosaic=0.0, scale=0.2, translate=0.1)


def predict_val(model, images: np.ndarray, bs: int = 200) -> list[np.ndarray]:
    out = []
    for i in range(0, len(images), bs):
        chunk = [np.repeat(im[..., None], 3, 2) for im in images[i:i + bs]]
        for r in model.predict(chunk, imgsz=128, conf=0.001, iou=0.5, max_det=20, verbose=False, device=0 if torch.cuda.is_available() else "cpu"):
            b = r.boxes
            out.append(np.concatenate([b.cls.cpu().numpy()[:, None], b.conf.cpu().numpy()[:, None], b.xyxy.cpu().numpy()], 1).astype(np.float32))
    return out


def run(mode: str, yaml, epochs: int, val_imgs, val_boxes, bs: int, log=print) -> dict:
    from ultralytics import YOLO

    project = SYLLABUS_RUNS / "det_yolov8"
    t0 = time.time()
    model = YOLO("yolov8n.pt" if mode == "pretrained" else "yolov8n.yaml")
    model.train(data=str(yaml), epochs=epochs, imgsz=128, batch=bs, device=0 if torch.cuda.is_available() else "cpu", workers=2, seed=0,
                project=str(project), name=mode, exist_ok=True, pretrained=(mode == "pretrained"), plots=False, verbose=False,
                amp=torch.cuda.is_available(), patience=epochs, **AUG)
    seconds = time.time() - t0
    best = YOLO(str(project / mode / "weights" / "best.pt"))
    own = metrics.evaluate(predict_val(best, val_imgs), val_boxes)
    theirs = best.val(data=str(yaml), imgsz=128, batch=bs, verbose=False, plots=False, device=0 if torch.cuda.is_available() else "cpu")
    log(f"{mode}: our mAP@0.5 {own['map50']:.3f}, mAP@[.5:.95] {own['map50_95']:.3f}; ultralytics mAP@0.5 {theirs.box.map50:.3f}")
    return {"mode": mode, "epochs": epochs, "train_seconds": round(seconds), "params": sum(p.numel() for p in best.model.parameters()),
            "ultralytics_map50": float(theirs.box.map50), "ultralytics_map50_95": float(theirs.box.map), **own}


def figure(res: dict, scratch: dict | None):
    import matplotlib.pyplot as plt

    style()
    names, m50, m95 = [], [], []
    if scratch:
        names.append("our YoloLite\n(from scratch)")
        m50.append(scratch["map50"]); m95.append(scratch["map50_95"])
    for mode, label in (("scratch", "YOLOv8n\nrandom init"), ("pretrained", "YOLOv8n\nCOCO weights")):
        names.append(label)
        m50.append(res[mode]["map50"]); m95.append(res[mode]["map50_95"])
    fig, axs = plt.subplots(1, 2, figsize=(11, 4.2))
    x = np.arange(len(names))
    axs[0].bar(x - 0.2, m50, 0.4, label="mAP@0.5")
    axs[0].bar(x + 0.2, m95, 0.4, label="mAP@[0.5:0.95]")
    axs[0].set_xticks(x, names)
    axs[0].set(ylim=(0, 1.05), title="Same scenes, same metric")
    axs[0].legend()
    for mode, c in (("scratch", "C1"), ("pretrained", "C2")):
        axs[1].bar([int(i) + (-0.2 if mode == "scratch" else 0.2) for i in range(10)], [v or 0 for v in res[mode]["ap50_per_class"]], 0.4, color=c, label=mode)
    axs[1].set(xticks=range(10), xlabel="digit", ylabel="AP@0.5", ylim=(0, 1.05), title="Per-digit AP@0.5 of the two YOLOv8n runs")
    axs[1].legend()
    fig.tight_layout()
    return fig


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--epochs", type=int, default=30)
    ap.add_argument("--train", type=int, default=20000)
    ap.add_argument("--val", type=int, default=2000)
    ap.add_argument("--smoke", action="store_true")
    a = ap.parse_args()
    epochs, n_train, n_val = (1, 200, 100) if a.smoke else (a.epochs, a.train, a.val)
    root = default_root() / ("smoke" if a.smoke else "full")
    if root.exists():
        shutil.rmtree(root)
    yaml = export_yolo_dataset(root, n_train, n_val)
    val_imgs, val_boxes = build_scenes(n_val, "val")             # identical to the images just exported (same seed)
    bs = 16 if a.smoke else 64
    res = {mode: run(mode, yaml, epochs, val_imgs, val_boxes, bs) for mode in ("scratch", "pretrained")}
    scratch = SYLLABUS_RUNS / "det_scratch" / "results.json"
    import json

    mine = json.loads(scratch.read_text()) if scratch.exists() else None
    out = {"train_scenes": n_train, "val_scenes": n_val, "val_objects": int(sum(len(b) for b in val_boxes)), "augmentation": AUG, **res}
    save_results("det_yolov8", out)
    if not a.smoke:
        save_figure(figure(res, mine), "det_yolov8")
    shutil.rmtree(root, ignore_errors=True)                       # the scenes are regenerated from the seed; keep the repo and the kernel output small


if __name__ == "__main__":
    main()
