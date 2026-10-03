"""Shared helpers for the syllabus experiments: device, MNIST tensors, result files and figure output."""
import json
from pathlib import Path

import torch

from src.common import PROC_DIR, ROOT, RUNS_DIR

SYLLABUS_RUNS = RUNS_DIR / "syllabus"
FIGURES = ROOT / "report" / "figures"


def device() -> torch.device:
    return torch.device("cuda" if torch.cuda.is_available() else "cpu")


def seed_all(seed: int = 0) -> None:
    torch.manual_seed(seed)
    torch.cuda.manual_seed_all(seed)


def load_mnist(train: bool, limit: int | None = None) -> tuple[torch.Tensor, torch.Tensor]:
    """(images float32 (N,1,28,28) in [0,1], labels int64). Downloads once if missing (the Kaggle kernel has internet)."""
    import torchvision

    ds = torchvision.datasets.MNIST(PROC_DIR / "mnist", train=train, download=True)
    x, y = ds.data[:limit].float().div(255).unsqueeze(1), ds.targets[:limit].long()
    return x, y


def run_dir(name: str) -> Path:
    d = SYLLABUS_RUNS / name
    d.mkdir(parents=True, exist_ok=True)
    return d


def save_results(name: str, results: dict) -> None:
    (run_dir(name) / "results.json").write_text(json.dumps(results, indent=2), encoding="utf-8")


def load_results(name: str) -> dict:
    return json.loads((SYLLABUS_RUNS / name / "results.json").read_text(encoding="utf-8"))


def save_figure(fig, name: str) -> Path:
    """Figures live next to the existing report figures; the 'syllabus_' prefix keeps them apart."""
    FIGURES.mkdir(parents=True, exist_ok=True)
    path = FIGURES / f"syllabus_{name}.png"
    fig.savefig(path, dpi=130, bbox_inches="tight")
    return path


def style() -> None:
    import matplotlib.pyplot as plt

    plt.rcParams.update({"figure.dpi": 110, "axes.spines.top": False, "axes.spines.right": False, "axes.grid": True, "grid.alpha": .25})


def image_grid(images, nrow: int, ax=None, title: str | None = None):
    """Draw a batch (N,1,H,W) in [0,1] as one tiled picture on `ax`."""
    import matplotlib.pyplot as plt
    import torchvision.utils as vu

    if ax is None:
        _, ax = plt.subplots()
    grid = vu.make_grid(images.detach().cpu().clamp(0, 1), nrow=nrow, padding=1, pad_value=0.5)
    ax.imshow(grid[0], cmap="gray", vmin=0, vmax=1)
    ax.axis("off")
    if title:
        ax.set_title(title, fontsize=10)
    return ax
