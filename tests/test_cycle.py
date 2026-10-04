"""The one-command cycle, with a fake Kaggle. The registry, the gate, the data checks and the models are real (the real v1 stands in for the model the
kernel would return), so these tests exercise everything except the network."""
import hashlib
import json
import pickle
import shutil
from pathlib import Path

import pytest

from src.flywheel import cycle, registry
from src.flywheel.cycle import Config, CycleError, run_cycle
from src.flywheel.onnx_eval import as_array

REAL = Path(__file__).resolve().parents[1] / "models" / "v1"
SAMPLES = json.loads((REAL / "samples.json").read_text(encoding="utf-8"))
CLASSES = json.loads((REAL / "meta.json").read_text(encoding="utf-8"))["classes"]


class FakeKaggle:
    """Records what the cycle asks Kaggle to do and plays back a scripted kernel."""

    def __init__(self, statuses=("RUNNING", "COMPLETE"), user="tester"):
        self.user, self.statuses, self.calls, self.kernel_files = user, list(statuses), [], {}

    def publish_dataset(self, folder, message):
        self.calls.append(("dataset", json.loads((folder / "dataset-metadata.json").read_text(encoding="utf-8"))["id"]))

    def publish_code(self):
        self.calls.append(("code",))

    def push_kernel(self, folder):
        meta = json.loads((folder / "kernel-metadata.json").read_text(encoding="utf-8"))
        self.kernel_files = {"meta": meta, "script": (folder / "run_finetune.py").read_text(encoding="utf-8")}
        self.calls.append(("kernel", meta["id"]))

    def kernel_status(self, ref):
        self.calls.append(("status", ref))
        return "KernelWorkerStatus." + (self.statuses.pop(0) if len(self.statuses) > 1 else self.statuses[0])

    def download_output(self, ref, dest):
        version = ref.rsplit("-", 1)[1]                                         # ...-finetune-v2
        out = dest / "out"
        (out / "models" / version).mkdir(parents=True)
        for name in ("sketch.onnx", "meta.json", "samples.json"):
            shutil.copy(REAL / name, out / "models" / version / name)
        (out / "runs" / "v3" / "ft").mkdir(parents=True)
        (out / "runs" / "v3" / "ft" / "best.pt").write_bytes(b"checkpoint")
        (out / "runs" / "v3" / "ft" / "adaptation.json").write_text(json.dumps({"heldout_user_drawings": 18}), encoding="utf-8")
        (out / "steps.json").write_text(json.dumps([{"step": s, "exit": 0, "seconds": 1} for s in ("download", "finetune", "export")]), encoding="utf-8")
        self.calls.append(("output", ref))


def write_records(database_url, out, n=90):
    """Stand-in for the app's export: real held-out sketches as consented drawings."""
    rows = [{"uid": hashlib.sha256(f"c:{i}".encode()).hexdigest()[:16], "label": s["label"], "strokes": s["strokes"], "source": "teach",
             "input_type": "mouse" if i % 2 else "touch"} for i, s in enumerate(SAMPLES[:n])]
    out.write_text("\n".join(json.dumps(r) for r in rows), encoding="utf-8")
    return len(rows)


@pytest.fixture(scope="module")
def heldout(tmp_path_factory):
    path = tmp_path_factory.mktemp("held") / "heldout.pkl"
    pickle.dump({"sketches": [as_array(s["strokes"]) for s in SAMPLES], "labels": [CLASSES.index(s["label"]) for s in SAMPLES], "classes": CLASSES}, open(path, "wb"))
    return path


@pytest.fixture
def cfg(tmp_path, heldout):
    models = tmp_path / "models"
    shutil.copytree(REAL, models / "v1")
    registry.register("v1", models)
    registry.set_checkpoint("v1", "tester/base-kernel", "runs/v3/fusion_ghost_xl/best.pt", models)
    return Config(models_dir=models, work_dir=tmp_path / "work", results_dir=tmp_path / "results", heldout=heldout, user="tester", min_heldout=5,
                  per_class=3, poll_seconds=0, exporter=write_records, ask=lambda q: False)


# ---------------------------------------------------------------- guard rails

def test_it_refuses_to_judge_on_too_few_held_out_drawings_and_never_touches_kaggle(cfg):
    cfg.min_heldout = 30
    kaggle = FakeKaggle()
    with pytest.raises(CycleError, match="held-out real drawings.*at least 30"):
        run_cycle(cfg, kaggle)
    assert kaggle.calls == []


def test_a_dry_run_only_exports_and_checks(cfg):
    kaggle = FakeKaggle()
    cfg.dry_run = True
    state = run_cycle(cfg, kaggle, log=lambda *_: None)
    assert kaggle.calls == [] and state["exported"] == 90 and state["data"]["train"] + state["data"]["heldout"] == 90
    assert state["data"]["by_input_type"] == {"mouse": 45, "touch": 45} and registry.load(cfg.models_dir)["active"] == "v1"


def test_a_model_with_no_recorded_checkpoint_cannot_be_fine_tuned(cfg):
    reg = registry.load(cfg.models_dir)
    del reg["versions"]["v1"]["checkpoint"]
    registry.save(reg, cfg.models_dir)
    with pytest.raises(CycleError, match="set-checkpoint"):
        run_cycle(cfg, FakeKaggle(), log=lambda *_: None)


def test_new_versions_are_numbered_after_the_highest_registered(cfg):
    assert cycle.next_version(cfg.models_dir) == "v2"
    reg = registry.load(cfg.models_dir)
    reg["versions"]["v7"] = dict(reg["versions"]["v1"])
    registry.save(reg, cfg.models_dir)
    assert cycle.next_version(cfg.models_dir) == "v8"


# ---------------------------------------------------------------- the full cycle

def test_the_full_cycle_publishes_trains_installs_compares_and_promotes_on_request(cfg):
    cfg.promote = True
    kaggle = FakeKaggle(statuses=["COMPLETE", "RUNNING", "RUNNING", "COMPLETE"])          # the first COMPLETE is the PREVIOUS run's: it must be ignored
    state = run_cycle(cfg, kaggle, log=lambda *_: None)

    order = [c[0] for c in kaggle.calls]
    assert order[:4] == ["dataset", "code", "kernel", "status"] and order[-1] == "output"
    assert order.count("status") == 4                                                      # it kept waiting past the stale COMPLETE
    assert ("dataset", "tester/sketch-evolution-userdata") in kaggle.calls and ("kernel", "tester/sketch-evolution-finetune-v2") in kaggle.calls

    meta = kaggle.kernel_files["meta"]
    assert meta["kernel_sources"] == ["tester/base-kernel"] and meta["enable_gpu"] and "tester/sketch-evolution-userdata" in meta["dataset_sources"]
    assert 'NEW_VERSION = "v2"' in kaggle.kernel_files["script"] and 'BASE_PATH = "runs/v3/fusion_ghost_xl/best.pt"' in kaggle.kernel_files["script"]

    reg = registry.load(cfg.models_dir)
    entry = reg["versions"]["v2"]
    assert entry["parent"] == "v1" and entry["checkpoint"] == {"kernel": "tester/sketch-evolution-finetune-v2", "path": "runs/v3/ft/best.pt"}
    assert state["gate_passed"] is True and state["promoted"] is True and reg["active"] == "v2"
    assert (cfg.results_dir / "gate_v1_to_v2.json").exists() and (cfg.results_dir / "adaptation_v2.json").exists()
    gate = json.loads((cfg.results_dir / "gate_v1_to_v2.json").read_text(encoding="utf-8"))["comparison"]["verdict"]
    assert gate["quickdraw"]["n"] > 0 and gate["user"]["n"] > 0                            # both yardsticks were really measured


def test_it_asks_before_promoting_and_a_no_leaves_the_candidate_registered(cfg):
    questions = []
    cfg.ask = lambda q: questions.append(q) or False
    state = run_cycle(cfg, FakeKaggle(), log=lambda *_: None)
    reg = registry.load(cfg.models_dir)
    assert len(questions) == 1 and "v2" in questions[0] and state["promoted"] is False
    assert reg["active"] == "v1" and "v2" in reg["versions"]


def test_no_promote_never_asks(cfg):
    cfg.promote = False
    cfg.ask = lambda q: pytest.fail("must not ask")
    assert run_cycle(cfg, FakeKaggle(), log=lambda *_: None)["promoted"] is False


def test_a_failed_gate_keeps_the_candidate_out_even_with_promote(cfg):
    cfg.promote, cfg.tolerance = True, -0.2                                                # the candidate would have to beat the live model by 20 points
    state = run_cycle(cfg, FakeKaggle(), log=lambda *_: None)
    assert state["gate_passed"] is False and state["promoted"] is False and registry.load(cfg.models_dir)["active"] == "v1"


# ---------------------------------------------------------------- failure and resume

def test_a_kernel_error_stops_with_advice_and_a_resume_skips_finished_steps(cfg, tmp_path):
    run_dir = tmp_path / "run"
    first = FakeKaggle(statuses=["RUNNING", "ERROR"])
    with pytest.raises(CycleError, match="ended with KernelWorkerStatus.ERROR.*--resume"):
        run_cycle(cfg, first, run_dir, log=lambda *_: None)
    assert [c[0] for c in first.calls].count("dataset") == 1
    assert json.loads((run_dir / "state.json").read_text(encoding="utf-8"))["done"] == ["export", "check", "data", "code"]

    second = FakeKaggle(statuses=["RUNNING", "COMPLETE"])
    state = run_cycle(cfg, second, run_dir, log=lambda *_: None)
    assert "dataset" not in [c[0] for c in second.calls] and "code" not in [c[0] for c in second.calls]      # nothing re-uploaded
    assert state["version"] == "v2" and "v2" in registry.load(cfg.models_dir)["versions"]


def test_an_incomplete_kernel_output_is_caught(cfg):
    class Broken(FakeKaggle):
        def download_output(self, ref, dest):
            super().download_output(ref, dest)
            (dest / "out" / "runs" / "v3" / "ft" / "adaptation.json").unlink()

    with pytest.raises(CycleError, match="incomplete.*adaptation.json"):
        run_cycle(cfg, Broken(), log=lambda *_: None)


def test_a_kernel_step_that_failed_is_reported(cfg):
    class Failed(FakeKaggle):
        def download_output(self, ref, dest):
            super().download_output(ref, dest)
            (dest / "out" / "steps.json").write_text(json.dumps([{"step": "finetune", "exit": 1, "seconds": 3}]), encoding="utf-8")

    with pytest.raises(CycleError, match="kernel steps failed: finetune"):
        run_cycle(cfg, Failed(), log=lambda *_: None)
