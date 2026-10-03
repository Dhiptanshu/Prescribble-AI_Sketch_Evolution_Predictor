"""Which model version is live: read from models/registry.json (written by `python -m src.flywheel.registry`).

PRESCRIBBLE_MODEL_VERSION, when set, overrides the registry (an operator pinning a version). With no registry the answer is "v1", the
version that existed before the registry did.
"""
import json
from pathlib import Path

from app.classes import models_dir
from app.config import Settings

FALLBACK = "v1"


def read(folder: Path | None) -> dict | None:
    if folder is None or not (folder / "registry.json").is_file():
        return None
    try:
        return json.loads((folder / "registry.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def active_version(settings: Settings) -> str:
    if settings.model_version:
        return settings.model_version
    reg = read(models_dir(settings))
    return (reg or {}).get("active") or FALLBACK


def public_view(settings: Settings) -> dict:
    """What anyone may know about the models: which is live and the measured numbers of each, never file hashes or notes."""
    reg = read(models_dir(settings)) or {}
    active = active_version(settings)
    versions = [
        {"version": name, "live": name == active, "n_classes": v.get("n_classes"), "class_set": v.get("class_set"), "created": v.get("created"),
         "architecture": v.get("architecture"), "size_mb": v.get("size_mb"), "metrics": v.get("metrics", {})}
        for name, v in (reg.get("versions") or {}).items()
    ]
    return {"active": active, "versions": versions}
