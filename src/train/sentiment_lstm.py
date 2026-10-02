"""Module IV side task: neural sentiment analysis (IMDB reviews) with an LSTM, in PyTorch.

python -m src.train.sentiment_lstm [--epochs 4]
Data: the Keras-hosted IMDB npz (25k train / 25k test reviews, already tokenised to word indices). No TensorFlow needed.
"""
import argparse
import json
import urllib.request

import numpy as np
import torch
import torch.nn as nn

from src.common import PROC_DIR, RUNS_DIR

URL = "https://storage.googleapis.com/tensorflow/tf-keras-datasets/imdb.npz"
VOCAB, MAXLEN = 10000, 200


def load():
    path = PROC_DIR / "imdb.npz"
    if not path.exists():
        PROC_DIR.mkdir(parents=True, exist_ok=True)
        urllib.request.urlretrieve(URL, path)
    d = np.load(path, allow_pickle=True)

    def prep(seqs):
        out = np.zeros((len(seqs), MAXLEN), np.int64)
        for i, s in enumerate(seqs):
            s = [w if w < VOCAB else 2 for w in s][-MAXLEN:]       # keep the end of long reviews, 2 = unknown
            out[i, -len(s):] = s                                   # left-pad so the LSTM ends on real words
        return torch.from_numpy(out)

    return prep(d["x_train"]), torch.from_numpy(d["y_train"]).float(), prep(d["x_test"]), torch.from_numpy(d["y_test"]).float()


class SentimentLSTM(nn.Module):
    def __init__(self):
        super().__init__()
        self.emb = nn.Embedding(VOCAB, 64, padding_idx=0)
        self.lstm = nn.LSTM(64, 64, batch_first=True)
        self.out = nn.Sequential(nn.Dropout(0.3), nn.Linear(64, 1))

    def forward(self, x):
        h, _ = self.lstm(self.emb(x))
        return self.out(h[:, -1]).squeeze(1)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--epochs", type=int, default=4)
    a = ap.parse_args()
    torch.manual_seed(0)
    xtr, ytr, xte, yte = load()
    dev = "cuda" if torch.cuda.is_available() else "cpu"
    m = SentimentLSTM().to(dev)
    opt = torch.optim.Adam(m.parameters(), lr=2e-3)
    loss_fn = nn.BCEWithLogitsLoss()
    log = []
    for ep in range(1, a.epochs + 1):
        m.train()
        perm = torch.randperm(len(xtr))
        for i in range(0, len(xtr), 128):
            idx = perm[i : i + 128]
            loss = loss_fn(m(xtr[idx].to(dev)), ytr[idx].to(dev))
            opt.zero_grad()
            loss.backward()
            nn.utils.clip_grad_norm_(m.parameters(), 1.0)
            opt.step()
        m.eval()
        with torch.no_grad():
            acc = np.mean([((m(xte[i : i + 512].to(dev)) > 0).float().cpu() == yte[i : i + 512]).float().mean().item()
                           for i in range(0, len(xte), 512)])
        log.append({"epoch": ep, "test_acc": float(acc)})
        print(f"epoch {ep} test acc {acc:.4f}", flush=True)
    out = RUNS_DIR / "sentiment"
    out.mkdir(parents=True, exist_ok=True)
    json.dump(log, open(out / "results.json", "w"), indent=2)


if __name__ == "__main__":
    main()
