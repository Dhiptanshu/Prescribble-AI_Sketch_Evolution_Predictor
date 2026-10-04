"""Registry tests. Real model files are reused: the real v1 is copied under other names to stand in for 'a new version'."""
import json
import pickle
import shutil
from pathlib import Path

import pytest

from src.flywheel import registry
from src.flywheel.onnx_eval import OnnxModel, as_array, evaluate, mean_top5
from src.flywheel.registry import RegistryError

REAL = Path(__file__).resolve().parents[1] / "models" / "v1"


@pytest.fixture
def models(tmp_path):
    """A models/ folder holding a registered v1 (a copy of the real one)."""
    shutil.copytree(REAL, tmp_path / "v1")
    registry.register("v1", tmp_path)
    return tmp_path


def clone(models: Path, name: str) -> None:
    shutil.copytree(models / "v1", models / name)


@pytest.fixture(scope="module")
def heldout(tmp_path_factory):
    """The real held-out sketches shipped with v1, in the pickle format the training kernel writes."""
    samples = json.loads((REAL / "samples.json").read_text(encoding="utf-8"))
    classes = json.loads((REAL / "meta.json").read_text(encoding="utf-8"))["classes"]
    path = tmp_path_factory.mktemp("heldout") / "heldout.pkl"
    pickle.dump({"sketches": [as_array(s["strokes"]) for s in samples], "labels": [classes.index(s["label"]) for s in samples], "classes": classes}, open(path, "wb"))
    return path


# ---------------------------------------------------------------- register and verify

def test_the_first_registered_model_is_live(models):
    reg = registry.load(models)
    assert reg["active"] == "v1" and reg["versions"]["v1"]["n_classes"] == 30 and len(reg["versions"]["v1"]["sha256"]) == 64
    assert reg["versions"]["v1"]["metrics"]["quickdraw_test_top5_at_30"] > 0.9            # read from the model's own measured results
    assert registry.verify("v1", models) == []


def test_registering_needs_a_complete_folder_and_is_idempotent(models):
    (models / "v2").mkdir()
    with pytest.raises(RegistryError, match="missing"):
        registry.register("v2", models)
    first = registry.load(models)["versions"]["v1"]
    assert registry.register("v1", models) == first                                      # same bytes: a no-op


def test_a_registered_version_cannot_change_its_bytes(models):
    with open(models / "v1" / "sketch.onnx", "ab") as f:
        f.write(b"\0")
    with pytest.raises(RegistryError, match="immutable"):
        registry.register("v1", models)
    assert any("hash" in p for p in registry.verify("v1", models))                        # and serving it is refused


def test_verify_runs_the_model(models):
    clone(models, "v1b")
    registry.register("v1b", models)
    assert registry.verify("v1b", models) == []
    (models / "v1b" / "sketch.onnx").write_bytes(b"not a model")
    problems = registry.verify("v1b", models)
    assert problems and any("hash" in p for p in problems)


# ---------------------------------------------------------------- promotion gate

def test_promoting_a_model_that_holds_up_makes_it_live(models, heldout):
    clone(models, "v1b")
    registry.register("v1b", models, parent="v1")
    report = registry.promote("v1b", models, heldout=heldout)
    q = report["comparison"]["verdict"]["quickdraw"]
    assert report["passed"] and registry.load(models)["active"] == "v1b" and q["delta"] == pytest.approx(0, abs=1e-9)
    assert q["n"] == 90 and q["candidate_unmasked_n"] == q["n"] and q["active_top5"] > 0.8                                        # a real measurement on real sketches, not a stub
    last = registry.load(models)["history"][-1]
    assert last["event"] == "promoted" and last["gate"] == "passed" and last["previous"] == "v1"


def test_a_candidate_that_is_not_better_is_refused_when_improvement_is_demanded(models, heldout):
    clone(models, "v1b")
    registry.register("v1b", models)
    with pytest.raises(RegistryError, match="gate failed"):
        registry.promote("v1b", models, heldout=heldout, tolerance=-0.2)                 # must beat the live model by 20 points: impossible for a copy
    assert registry.load(models)["active"] == "v1"


def test_forcing_past_a_failed_gate_is_allowed_and_recorded(models, heldout):
    clone(models, "v1b")
    registry.register("v1b", models)
    registry.promote("v1b", models, heldout=heldout, tolerance=-0.2, force=True)
    assert registry.load(models)["active"] == "v1b"
    assert "FORCED" in registry.load(models)["history"][-1]["gate"]


def test_a_gate_needs_the_heldout_set(models):
    clone(models, "v1b")
    registry.register("v1b", models)
    with pytest.raises(RegistryError, match="--heldout"):
        registry.promote("v1b", models)


def test_dropping_a_class_the_live_model_knows_fails_the_gate(models, heldout, monkeypatch):
    clone(models, "v1b")
    registry.register("v1b", models)
    real_init = OnnxModel.__init__

    def init(self, version, models_dir=registry.MODELS):
        real_init(self, version, models_dir)
        if version == "v1b":
            self.classes = [c if c != "cat" else "renamed" for c in self.classes]         # as if the new model lost 'cat'
    monkeypatch.setattr(OnnxModel, "__init__", init)
    with pytest.raises(RegistryError, match="gate failed"):
        registry.promote("v1b", models, heldout=heldout)


def test_user_drawings_are_a_second_gate_only_when_there_are_enough(models, heldout, tmp_path):
    clone(models, "v1b")
    registry.register("v1b", models)
    samples = json.loads((REAL / "samples.json").read_text(encoding="utf-8"))
    path = tmp_path / "user.jsonl"
    rows = [{"uid": f"{i:08x}" + "0" * 8, "label": s["label"], "strokes": s["strokes"]} for i, s in enumerate(samples[:12])]
    path.write_text("\n".join(json.dumps(r) for r in rows), encoding="utf-8")
    report = registry.promote("v1b", models, heldout=heldout, user_eval=path, min_user=30)
    assert "skipped" in report["comparison"]["verdict"]["user"]                           # 12 drawings are too few to judge by


def test_rollback_returns_to_the_previous_version(models, heldout):
    clone(models, "v1b")
    registry.register("v1b", models)
    registry.promote("v1b", models, heldout=heldout)
    assert registry.rollback(models) == "v1" and registry.load(models)["active"] == "v1"
    assert registry.load(models)["history"][-1]["event"] == "rolled_back"
    with pytest.raises(RegistryError, match="already live"):
        registry.promote("v1", models, heldout=heldout)


def test_rollback_with_nothing_to_go_back_to(models):
    with pytest.raises(RegistryError, match="no earlier"):
        registry.rollback(models)


# ---------------------------------------------------------------- the evaluator

def test_masking_makes_models_comparable_on_shared_classes(models):
    m = OnnxModel("v1", models)
    samples = json.loads((REAL / "samples.json").read_text(encoding="utf-8"))
    sk, lb = [as_array(s["strokes"]) for s in samples], [s["label"] for s in samples]
    free = evaluate(m, sk, lb)
    masked = evaluate(m, sk, lb, restrict_to={"cat", "dog", "house"})
    assert free["n"] == 90 and masked["n"] == 9                                           # only those classes' sketches are scored
    assert mean_top5(masked) >= 0.9                                                       # with three choices, Top-5 is nearly always right


def test_only_labels_picks_the_sketches_and_restrict_to_picks_the_answers(models):
    """The unmasked figure must be about the SAME sketches as the masked one, with the model free to answer with any class."""
    m = OnnxModel("v1", models)
    samples = json.loads((REAL / "samples.json").read_text(encoding="utf-8"))
    sk, lb = [as_array(s["strokes"]) for s in samples], [s["label"] for s in samples]
    three = {"cat", "dog", "house"}
    masked = evaluate(m, sk, lb, restrict_to=three)
    free = evaluate(m, sk, lb, only_labels=three)
    assert masked["n"] == free["n"] == 9                                                  # the same nine sketches
    assert mean_top5(free) <= mean_top5(masked) + 1e-9                                    # ruling out 27 more classes can only be harder or equal
    assert evaluate(m, sk, lb)["n"] == 90                                                 # neither switch: every sketch of a known class
