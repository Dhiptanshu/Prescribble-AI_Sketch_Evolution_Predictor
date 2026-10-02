"""Multilayer perceptron written from scratch in NumPy (manual forward + backpropagation). Module I.

Architecture: input -> [Linear -> ReLU]*k -> Linear -> softmax cross-entropy. Optimiser: SGD with momentum.
"""
import numpy as np


class MLP:
    def __init__(self, sizes, seed: int = 0, lr: float = 0.05, momentum: float = 0.9, l2: float = 1e-5):
        rng = np.random.default_rng(seed)
        self.W = [rng.normal(0, np.sqrt(2.0 / a), (a, b)).astype(np.float32) for a, b in zip(sizes[:-1], sizes[1:])]  # He init
        self.b = [np.zeros(b, np.float32) for b in sizes[1:]]
        self.vW = [np.zeros_like(w) for w in self.W]
        self.vb = [np.zeros_like(b) for b in self.b]
        self.lr, self.mom, self.l2 = lr, momentum, l2

    # ---- forward -------------------------------------------------------------------------
    def forward(self, x):
        acts = [x]
        for i, (W, b) in enumerate(zip(self.W, self.b)):
            z = acts[-1] @ W + b
            acts.append(np.maximum(z, 0) if i < len(self.W) - 1 else z)
        return acts

    @staticmethod
    def softmax(z):
        z = z - z.max(1, keepdims=True)
        e = np.exp(z)
        return e / e.sum(1, keepdims=True)

    def predict_proba(self, x):
        return self.softmax(self.forward(x)[-1])

    # ---- backprop ------------------------------------------------------------------------
    def step(self, x, y):
        acts = self.forward(x)
        p = self.softmax(acts[-1])
        n = len(x)
        loss = -np.log(p[np.arange(n), y] + 1e-9).mean()
        delta = p
        delta[np.arange(n), y] -= 1.0
        delta /= n                                         # dL/dz_last
        for i in reversed(range(len(self.W))):
            gW = acts[i].T @ delta + self.l2 * self.W[i]
            gb = delta.sum(0)
            if i > 0:
                delta = (delta @ self.W[i].T) * (acts[i] > 0)   # ReLU derivative
            self.vW[i] = self.mom * self.vW[i] - self.lr * gW
            self.vb[i] = self.mom * self.vb[i] - self.lr * gb
            self.W[i] += self.vW[i]
            self.b[i] += self.vb[i]
        return float(loss)

    def fit(self, X, y, epochs=10, bs=128, seed=0, on_epoch=None):
        rng = np.random.default_rng(seed)
        for ep in range(1, epochs + 1):
            idx = rng.permutation(len(X))
            losses = [self.step(X[idx[i : i + bs]], y[idx[i : i + bs]]) for i in range(0, len(X) - bs + 1, bs)]
            if on_epoch:
                on_epoch(ep, float(np.mean(losses)))

    def accuracy(self, X, y, k: int = 1):
        p = self.predict_proba(X)
        topk = np.argsort(-p, axis=1)[:, :k]
        return float((topk == y[:, None]).any(1).mean())

    def grad_check(self, x, y, eps: float = 1e-3):
        """Compare analytic vs numeric gradient on a few weights (used in the notebook to prove backprop is right)."""
        saved = ([w.copy() for w in self.W], [b.copy() for b in self.b], self.lr, self.mom, self.l2)
        self.lr, self.mom, self.l2 = 1.0, 0.0, 0.0
        W0 = self.W[0].copy()
        self.step(x, y)
        analytic = (W0 - self.W[0])[0, :5]                 # lr=1 => update = gradient
        self.W, self.b = [w.copy() for w in saved[0]], [b.copy() for b in saved[1]]
        self.lr, self.mom, self.l2 = saved[2:]

        def loss():
            p = self.softmax(self.forward(x)[-1])
            return -np.log(p[np.arange(len(x)), y] + 1e-9).mean()

        numeric = []
        for j in range(5):
            self.W[0][0, j] += eps
            lp = loss()
            self.W[0][0, j] -= 2 * eps
            lm = loss()
            self.W[0][0, j] += eps
            numeric.append((lp - lm) / (2 * eps))
        return analytic, np.array(numeric)
