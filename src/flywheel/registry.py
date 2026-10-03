"""The model registry: models/registry.json, the one file that says which model version is live.

    python -m src.flywheel.registry list
    python -m src.flywheel.registry register v2 [--parent v1] [--notes "..."]
    python -m src.flywheel.registry promote v2 --heldout data/processed/v2/heldout.pkl [--user-eval file.jsonl] [--force]
    python -m src.flywheel.registry rollback

A version folder (models/<version>/) is immutable once registered: its ONNX file is hashed, and every promotion re-checks the hash. The apps read
`active` from this file (the API on startup, the browser and the widget at load time), so promoting a version ships it with no app change.
Promotion is gated: the candidate must load and answer correctly, and must not be worse than the live model on held-out sketches of the
classes both know. Overriding a failed gate needs --force and is recorded in the history.
"""
import argparse
import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

from src.common import ROOT

MODELS = ROOT / "models"
REQUIRED = ("sketch.onnx", "meta.json", "results.json", "samples.json")
SCHEMA = 1


class RegistryError(Exception):
    pass


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def path_of(models_dir: Path) -> Path:
    return models_dir / "registry.json"


def load(models_dir: Path = MODELS) -> dict:
    p = path_of(models_dir)
    if not p.exists():
        return {"schema": SCHEMA, "active": None, "versions": {}, "history": []}
    return json.loads(p.read_text(encoding="utf-8"))


def save(reg: dict, models_dir: Path = MODELS) -> None:
    path_of(models_dir).write_text(json.dumps(reg, indent=2) + "\n", encoding="utf-8")


def _meta(models_dir: Path, version: str) -> dict:
    return json.loads((models_dir / version / "meta.json").read_text(encoding="utf-8"))


def register(version: str, models_dir: Path = MODELS, parent: str | None = None, notes: str = "") -> dict:
    """Add models/<version>/ to the registry as a candidate (not live). Re-registering the same files is a no-op; changed files are refused."""
    folder = models_dir / version
    missing = [f for f in REQUIRED if not (folder / f).is_file()]
    if missing:
        raise RegistryError(f"{version}: missing {', '.join(missing)}")
    reg = load(models_dir)
    digest = sha256(folder / "sketch.onnx")
    meta = _meta(models_dir, version)
    existing = reg["versions"].get(version)
    if existing:
        if existing["sha256"] != digest:
            raise RegistryError(f"{version} is already registered with different model bytes; versions are immutable, use a new version name")
        return existing
    results = meta.get("test_results", {})
    entry = {
        "class_set": meta.get("class_set", "v1"), "n_classes": len(meta["classes"]), "sha256": digest, "created": _now(), "parent": parent,
        "architecture": meta.get("model"), "size_mb": meta.get("size_mb"), "latency_ms": meta.get("latency_ms"), "notes": notes,
        "metrics": {"quickdraw_test_top5_at_30": results.get("0.3", {}).get("top5"), "quickdraw_test_top1_at_100": results.get("1.0", {}).get("top1")},
    }
    reg["versions"][version] = entry
    reg["history"].append({"at": _now(), "event": "registered", "version": version})
    if reg["active"] is None:                      # the very first model is live by definition
        reg["active"] = version
        reg["history"].append({"at": _now(), "event": "promoted", "version": version, "gate": "first model"})
    save(reg, models_dir)
    return entry


def verify(version: str, models_dir: Path = MODELS) -> list[str]:
    """Problems that make a registered version unfit to serve (empty list = fine): files, hash, class count, a real forward pass."""
    problems: list[str] = []
    reg = load(models_dir)
    entry = reg["versions"].get(version)
    if not entry:
        return [f"{version} is not registered"]
    folder = models_dir / version
    for f in REQUIRED:
        if not (folder / f).is_file():
            problems.append(f"missing {f}")
    if problems:
        return problems
    if sha256(folder / "sketch.onnx") != entry["sha256"]:
        problems.append("sketch.onnx does not match its registered hash")
    classes = _meta(models_dir, version)["classes"]
    if len(classes) != entry["n_classes"]:
        problems.append("class list differs from the registered one")
    try:
        import numpy as np

        from src.flywheel.onnx_eval import OnnxModel
        m = OnnxModel(version, models_dir)
        sample = json.loads((folder / "samples.json").read_text(encoding="utf-8"))[0]["strokes"]
        from src.flywheel.onnx_eval import as_array
        p = m.probabilities(as_array(sample), 1.0)
        if p.shape != (len(classes),) or abs(float(p.sum()) - 1.0) > 1e-3 or not np.isfinite(p).all():
            problems.append(f"the model's output is not a probability vector over {len(classes)} classes")
    except Exception as e:  # noqa: BLE001  (any failure to load or run means it cannot serve)
        problems.append(f"the model failed to run: {e}")
    return problems


def promote(version: str, models_dir: Path = MODELS, heldout: Path | None = None, user_eval: Path | None = None, force: bool = False,
            tolerance: float = 0.01, min_user: int = 30, per_class: int = 30) -> dict:
    """Make `version` the live model if it passes the gates. Returns the report; raises RegistryError when refused."""
    reg = load(models_dir)
    if version not in reg["versions"]:
        raise RegistryError(f"{version} is not registered")
    if reg["active"] == version:
        raise RegistryError(f"{version} is already live")
    problems = verify(version, models_dir)
    if problems:
        raise RegistryError(f"{version} failed verification: " + "; ".join(problems))
    report: dict = {"candidate": version, "active_before": reg["active"], "tolerance": tolerance}
    passed = True
    if reg["active"] is None:
        report["gate"] = "no live model to compare with"
    elif heldout is None:
        raise RegistryError("an accuracy gate needs --heldout (held-out QuickDraw sketches) to compare with the live model")
    else:
        from src.flywheel.gate import compare
        report["comparison"] = compare(models_dir, version, reg["active"], heldout, user_eval, tolerance, min_user, per_class)
        passed = report["comparison"]["passed"]
    report["passed"] = passed
    if not passed and not force:
        raise RegistryError("the accuracy gate failed (use --force to override, which is recorded): " + json.dumps(report["comparison"]["verdict"]))
    reg["active"] = version
    reg["history"].append({"at": _now(), "event": "promoted", "version": version, "previous": report["active_before"],
                           "gate": "passed" if passed else "FORCED past a failed gate", "report": report.get("comparison", {}).get("verdict")})
    save(reg, models_dir)
    return report


def rollback(models_dir: Path = MODELS) -> str:
    """Go back to the version that was live before the current one."""
    reg = load(models_dir)
    promotions = [h for h in reg["history"] if h["event"] == "promoted"]
    if len(promotions) < 2:
        raise RegistryError("there is no earlier version to roll back to")
    previous = promotions[-1].get("previous") or promotions[-2]["version"]
    problems = verify(previous, models_dir)
    if problems:
        raise RegistryError(f"cannot roll back to {previous}: " + "; ".join(problems))
    reg["active"] = previous
    reg["history"].append({"at": _now(), "event": "rolled_back", "version": previous, "from": promotions[-1]["version"]})
    save(reg, models_dir)
    return previous


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("list")
    r = sub.add_parser("register"); r.add_argument("version"); r.add_argument("--parent"); r.add_argument("--notes", default="")
    v = sub.add_parser("verify"); v.add_argument("version")
    p = sub.add_parser("promote"); p.add_argument("version"); p.add_argument("--heldout", type=Path); p.add_argument("--user-eval", type=Path)
    p.add_argument("--force", action="store_true"); p.add_argument("--tolerance", type=float, default=0.01)
    sub.add_parser("rollback")
    a = ap.parse_args(argv)
    try:
        if a.cmd == "list":
            reg = load()
            for name, e in reg["versions"].items():
                print(f"{'*' if name == reg['active'] else ' '} {name:6} {e['n_classes']:>3} classes  {e['architecture']}  top5@30%={e['metrics']['quickdraw_test_top5_at_30']}  {e['created']}")
        elif a.cmd == "register":
            print(json.dumps(register(a.version, parent=a.parent, notes=a.notes), indent=2))
        elif a.cmd == "verify":
            problems = verify(a.version)
            print("OK" if not problems else "\n".join(problems))
            return 1 if problems else 0
        elif a.cmd == "promote":
            print(json.dumps(promote(a.version, heldout=a.heldout, user_eval=a.user_eval, force=a.force, tolerance=a.tolerance), indent=2))
        elif a.cmd == "rollback":
            print("live version is now", rollback())
    except RegistryError as e:
        print("refused:", e, file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
