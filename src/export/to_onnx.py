"""Export a trained variant to ONNX (batch 1), verify against PyTorch and time it on CPU.

python -m src.export.to_onnx --model fusion_ghost
Writes models/<version>/sketch.onnx and meta.json (class names + real test results used by the web app).
--version v2 ships a new model without touching the app code (bump MODEL_VERSION in apps/web/src/lib/engine.tsx).
"""
import argparse
import json
import time

import numpy as np
import onnxruntime as ort
import torch
import torch.nn as nn

from src.common import CLASSES, IMG, MAX_PTS, RUNS_DIR, ROOT, SEQ_FEATS
from src.models.nets import build



class Wrapper(nn.Module):
    def __init__(self, net):
        super().__init__()
        self.net = net

    def forward(self, img, seq, length):
        logits, recon = self.net(img, seq, length)
        probs = torch.softmax(logits, dim=1)
        ghost = torch.sigmoid(recon) if recon is not None else torch.zeros_like(img)
        return probs, ghost


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", required=True)
    ap.add_argument("--version", default="v1")
    a = ap.parse_args()

    net = build(a.model)
    net.load_state_dict(torch.load(RUNS_DIR / a.model / "best.pt", map_location="cpu"))
    net.eval()
    wrap = Wrapper(net).eval()
    img = torch.rand(1, 1, IMG, IMG)
    seq = torch.rand(1, MAX_PTS, SEQ_FEATS)
    length = torch.tensor([17], dtype=torch.int64)

    OUT = ROOT / "models" / a.version
    OUT.mkdir(parents=True, exist_ok=True)
    path = OUT / "sketch.onnx"
    torch.onnx.export(wrap, (img, seq, length), str(path), input_names=["img", "seq", "length"],
                      output_names=["probs", "ghost"], opset_version=17, dynamo=False)

    sess = ort.InferenceSession(str(path), providers=["CPUExecutionProvider"])
    feed = {"img": img.numpy(), "seq": seq.numpy(), "length": length.numpy()}
    p_onnx, g_onnx = sess.run(None, feed)
    with torch.no_grad():
        p_t, g_t = wrap(img, seq, length)
    print("max |prob diff|:", float(np.abs(p_onnx - p_t.numpy()).max()), " max |ghost diff|:", float(np.abs(g_onnx - g_t.numpy()).max()))
    t0 = time.perf_counter()
    for _ in range(100):
        sess.run(None, feed)
    ms = (time.perf_counter() - t0) * 10
    size = path.stat().st_size / 1e6
    print(f"latency {ms:.1f} ms/prediction (CPU), model {size:.1f} MB")

    results = json.load(open(RUNS_DIR / a.model / "results.json"))
    json.dump({"model": a.model, "version": a.version, "classes": CLASSES, "img": IMG, "max_pts": MAX_PTS, "seq_feats": SEQ_FEATS,
               "test_results": results, "latency_ms": ms, "size_mb": size},
              open(OUT / "meta.json", "w"), indent=2)


if __name__ == "__main__":
    main()
