"""The object classes a model version can recognise, read from that version's own meta.json (single source of truth)."""
import json
from functools import lru_cache
from pathlib import Path

from app.config import Settings

_CANDIDATES = (Path(__file__).resolve().parent.parent.parent.parent / "models", Path("/app/models"))


def models_dir(settings: Settings) -> Path | None:
    if settings.models_dir:
        return settings.models_dir
    return next((p for p in _CANDIDATES if p.is_dir()), None)


@lru_cache(maxsize=16)
def _load(directory: str, version: str) -> frozenset[str] | None:
    meta = Path(directory) / version / "meta.json"
    if not meta.is_file():
        return None
    return frozenset(json.loads(meta.read_text(encoding="utf-8"))["classes"])


def known_classes(settings: Settings, version: str) -> frozenset[str] | None:
    """None means the model folder is not available here, so class names cannot be checked (length limits still apply)."""
    d = models_dir(settings)
    return _load(str(d), version) if d else None
