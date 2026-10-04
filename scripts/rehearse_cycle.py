"""Rehearse the flywheel cycle for real on Kaggle, with stand-in drawings, WITHOUT touching the real registry, database or live model.

python scripts/rehearse_cycle.py
The "user drawings" are the live model's own held-out QuickDraw samples (models/<live>/samples.json), so this proves the pipeline runs end to end
(dataset upload, kernel, fine-tune, download, install, gate) but its accuracy numbers mean nothing. Everything is written to a temporary copy of
models/ and results; the Kaggle datasets and the kernel it creates are the same ones a real run uses (a real run replaces their contents).
"""
import hashlib
import json
import shutil
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.flywheel import registry  # noqa: E402
from src.flywheel.cycle import Config, Kaggle, run_cycle  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent


def main() -> None:
    live = registry.load()["active"]
    tmp = Path(tempfile.mkdtemp(prefix="rehearsal-"))
    models = tmp / "models"
    models.mkdir()
    shutil.copy(ROOT / "models" / "registry.json", models / "registry.json")
    shutil.copytree(ROOT / "models" / live, models / live)
    samples = json.loads((models / live / "samples.json").read_text(encoding="utf-8"))

    def stand_in_export(_database_url: str, out: Path) -> int:
        rows = [{"uid": hashlib.sha256(f"rehearsal:{i}".encode()).hexdigest()[:16], "label": s["label"], "strokes": s["strokes"], "source": "rehearsal",
                 "input_type": "mouse"} for i, s in enumerate(samples)]
        out.write_text("\n".join(json.dumps(r) for r in rows), encoding="utf-8")
        return len(rows)

    cfg = Config(models_dir=models, work_dir=tmp / "work", results_dir=tmp / "results", user="dhiptanshumalik", min_heldout=30, per_class=10, promote=False,
                 poll_seconds=120, exporter=stand_in_export)
    print("rehearsal folder:", tmp, flush=True)
    state = run_cycle(cfg, Kaggle(cfg.user))
    print(json.dumps({k: v for k, v in state.items() if k != "summary"}, indent=2))
    print(state.get("summary", ""))


if __name__ == "__main__":
    main()
