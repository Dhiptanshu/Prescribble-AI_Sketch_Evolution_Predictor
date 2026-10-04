"""The whole flywheel in one command: consented drawings -> fine-tuned model on Kaggle -> comparison -> (asked) promotion.

    python -m src.flywheel.cycle                 # export, check, fine-tune on Kaggle (about an hour), compare, then ask before promoting
    python -m src.flywheel.cycle --dry-run       # only export and check: is there enough data, what would be sent?
    python -m src.flywheel.cycle --promote       # promote without asking if the gate passes (--no-promote: never)
    python -m src.flywheel.cycle --resume runs/flywheel/<run>   # carry on a run that was interrupted (finished steps are skipped)

Steps, each recorded in <run>/state.json so a run can be resumed:
  export     the consented, label-confirmed drawings of the live model's classes (apps/api: python -m app.cli export-training)
  check      enough held-out real drawings to judge by? (refuses otherwise: a gain measured on a handful of drawings means nothing)
  data       publish training.jsonl as the private Kaggle dataset sketch-evolution-userdata
  code       publish the current source as the Kaggle dataset sketch-evolution-data
  train      push the fine-tune kernel (kaggle/finetune/run_finetune.py) and wait for it
  download   fetch its output and check every step succeeded
  install    add the new version to models/ and the registry (a candidate, not live)
  compare    the registry's gate: shared classes on QuickDraw and on the held-out real drawings
  promote    make it live if the gate passed and you say yes
Nothing goes live without passing the gate and an explicit yes (or --promote).
"""
import argparse
import json
import os
import shutil
import subprocess
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from src.common import ROOT
from src.flywheel import dataset, registry
from src.flywheel.gate import compare

STEPS = ["export", "check", "data", "code", "train", "download", "install", "compare", "promote"]
EXPECTED_OUTPUT = ("models/{v}/sketch.onnx", "models/{v}/meta.json", "models/{v}/samples.json", "runs/v3/ft/adaptation.json", "runs/v3/ft/best.pt")
KERNEL_NAME, USERDATA_NAME, CODE_NAME = "sketch-evolution-finetune", "sketch-evolution-userdata", "sketch-evolution-data"
FIRST_LOOK_SECONDS = 600       # after a push Kaggle may still report the PREVIOUS run's final status; wait this long to see the new one start


class CycleError(Exception):
    """A step failed or a safeguard refused to continue; the message says what to do."""


# ------------------------------------------------------------------------------------------------ Kaggle

class Kaggle:
    """The few Kaggle operations the cycle needs, through the kaggle command line (swapped for a fake in the tests)."""

    def __init__(self, user: str, executable: str | None = None):
        self.user = user
        local = ROOT / ".venv-tools" / "Scripts" / "kaggle.exe"
        self.exe = executable or os.environ.get("KAGGLE") or (str(local) if local.exists() else "kaggle")

    def _run(self, *args: str, timeout: int = 1800) -> subprocess.CompletedProcess:
        return subprocess.run([self.exe, *args], capture_output=True, text=True, timeout=timeout)

    def publish_dataset(self, folder: Path, message: str) -> None:
        ref = json.loads((folder / "dataset-metadata.json").read_text(encoding="utf-8"))["id"]
        exists = self._run("datasets", "status", ref).stdout.strip().endswith("ready")
        done = self._run("datasets", "version" if exists else "create", "-p", str(folder), *(["-m", message] if exists else []), "--dir-mode", "zip")
        if done.returncode != 0:
            raise CycleError(f"publishing {ref} failed: {(done.stdout + done.stderr)[-400:]}")
        deadline = time.time() + 900
        while not self._run("datasets", "status", ref).stdout.strip().endswith("ready"):
            if time.time() > deadline:
                raise CycleError(f"{ref} was uploaded but never became ready")
            time.sleep(10)

    def publish_code(self) -> None:
        sys.path.insert(0, str(ROOT / "scripts"))
        import build_kaggle_dataset                                   # stages src/ and the small baselines into kaggle/dataset

        build_kaggle_dataset.main(self.user)
        self.publish_dataset(ROOT / "kaggle" / "dataset", "source for the fine-tune cycle")

    def push_kernel(self, folder: Path) -> None:
        done = self._run("kernels", "push", "-p", str(folder))
        if done.returncode != 0:
            raise CycleError(f"pushing the kernel failed: {(done.stdout + done.stderr)[-400:]}")

    def kernel_status(self, ref: str) -> str:
        words = self._run("kernels", "status", ref).stdout.strip().split()
        return words[-1].strip('"') if words else "UNKNOWN"

    def download_output(self, ref: str, dest: Path, tries: int = 3) -> None:
        """The CLI often exits 1 after downloading everything, so the caller checks for the expected files instead of trusting the exit code."""
        for _ in range(tries):
            self._run("kernels", "output", ref, "-p", str(dest), timeout=3600)
            if (dest / "out" / "steps.json").exists():
                return


# ------------------------------------------------------------------------------------------------ pieces

@dataclass
class Config:
    models_dir: Path = registry.MODELS
    work_dir: Path = ROOT / "runs" / "flywheel"
    database_url: str = f"sqlite:///{(ROOT / 'apps' / 'api' / 'prescribble.db').as_posix()}"
    user: str = "dhiptanshumalik"
    heldout: Path = ROOT / "data" / "processed" / "v3" / "heldout.pkl"
    results_dir: Path = ROOT / "docs" / "results"
    min_heldout: int = 30
    per_class: int = 10
    tolerance: float = 0.01
    promote: bool | None = None            # None = ask (when attached to a terminal), True = promote if the gate passes, False = never
    dry_run: bool = False
    poll_seconds: int = 300
    timeout_seconds: int = 8 * 3600
    exporter: object = None                # test hook: callable(database_url, out_path) -> number of drawings
    ask: object = field(default=None)      # test hook: callable(question) -> bool


def next_version(models_dir: Path) -> str:
    numbers = [int(v[1:]) for v in registry.load(models_dir)["versions"] if v[1:].isdigit()]
    return f"v{max(numbers, default=0) + 1}"


def export_drawings(database_url: str, out: Path) -> int:
    """Run the API's own export (consent, confirmed labels, duplicates, no identity) against the given database."""
    env = {**os.environ, "PRESCRIBBLE_DATABASE_URL": database_url}
    done = subprocess.run([sys.executable, "-m", "app.cli", "export-training", "--out", str(out)], cwd=ROOT / "apps" / "api", env=env,
                          capture_output=True, text=True)
    if done.returncode != 0:
        raise CycleError(f"exporting the drawings failed: {(done.stdout + done.stderr)[-400:]}")
    return sum(1 for line in out.read_text(encoding="utf-8").splitlines() if line.strip())


def check_data(jsonl: Path, classes: list[str], min_heldout: int) -> dict:
    """Count what a fine-tune could use and what it could be judged on, for the live model's classes."""
    records = [r for r in dataset.read_jsonl(jsonl) if r["label"] in set(classes)]
    train, held = dataset.split(records)
    summary = {"drawings": len(records), "train": len(train), "heldout": len(held), "classes_covered": len({r["label"] for r in records}),
               "by_input_type": {k: len(v) for k, v in dataset.by_input_type(records).items()}}
    if len(held) < min_heldout:
        raise CycleError(f"only {len(held)} held-out real drawings ({len(records)} drawings in total); at least {min_heldout} are needed to judge an "
                         f"adaptation honestly, so about {min_heldout * 5} drawings. Collect more at /teach and run this again.")
    return summary


def stage_userdata(folder: Path, jsonl: Path, user: str) -> Path:
    folder.mkdir(parents=True, exist_ok=True)
    shutil.copy(jsonl, folder / "training.jsonl")
    (folder / "dataset-metadata.json").write_text(json.dumps({
        "title": "Sketch Evolution Userdata", "id": f"{user}/{USERDATA_NAME}", "licenses": [{"name": "other"}],
        "description": "Consented, label-confirmed drawings exported from the app (no account identity)."}, indent=2), encoding="utf-8")
    return folder


def kernel_id(user: str, version: str) -> str:
    """One kernel per version, so a later cycle can use this one's output as its base without a kernel naming itself as its own source."""
    return f"{user}/{KERNEL_NAME}-{version}"


def stage_kernel(folder: Path, user: str, version: str, checkpoint: dict) -> Path:
    """The fine-tune kernel with this run's version name and base checkpoint written into the script."""
    folder.mkdir(parents=True, exist_ok=True)
    script = (ROOT / "kaggle" / "finetune" / "run_finetune.py").read_text(encoding="utf-8")
    script = script.replace('NEW_VERSION = "v4"', f'NEW_VERSION = "{version}"').replace('BASE_PATH = "runs/v3/fusion_ghost_xl/best.pt"', f'BASE_PATH = "{checkpoint["path"]}"')
    (folder / "run_finetune.py").write_text(script, encoding="utf-8")
    (folder / "kernel-metadata.json").write_text(json.dumps({
        "id": kernel_id(user, version), "title": f"Sketch Evolution Finetune {version.upper()}", "code_file": "run_finetune.py", "language": "python", "kernel_type": "script",
        "is_private": True, "enable_gpu": True, "enable_internet": True,
        "dataset_sources": [f"{user}/{CODE_NAME}", f"{user}/{USERDATA_NAME}"], "competition_sources": [], "kernel_sources": [checkpoint["kernel"]]}, indent=2),
        encoding="utf-8")
    return folder


def install_version(output: Path, version: str, parent: str, models_dir: Path, results_dir: Path, kernel: str) -> dict:
    """Copy the kernel's model into models/<version>, register it as a candidate and remember where its checkpoint lives."""
    out = output / "out"
    target = models_dir / version
    shutil.copytree(out / "models" / version, target)
    meta = json.loads((target / "meta.json").read_text(encoding="utf-8"))
    (target / "results.json").write_text(json.dumps(meta["test_results"]), encoding="utf-8")
    results_dir.mkdir(parents=True, exist_ok=True)
    shutil.copy(out / "runs" / "v3" / "ft" / "adaptation.json", results_dir / f"adaptation_{version}.json")
    entry = registry.register(version, models_dir, parent=parent, notes=f"fine-tuned from {parent} on consented user drawings (src/flywheel/cycle.py)")
    registry.set_checkpoint(version, kernel, "runs/v3/ft/best.pt", models_dir)
    problems = registry.verify(version, models_dir)
    if problems:
        raise CycleError(f"{version} was installed but failed verification: {'; '.join(problems)}")
    return entry


def summarise(report: dict) -> str:
    v = report["verdict"]
    lines = [f"shared classes: {v['shared_classes']}, dropped: {len(v['dropped_classes'])}"]
    q = v["quickdraw"]
    lines.append(f"QuickDraw held-out ({q['n']} sketches): live {q['active_top5']:.1%} -> candidate {q['candidate_top5']:.1%} ({q['delta']:+.1%} Top-5)")
    u = v.get("user", {})
    if "skipped" in u:
        lines.append(f"real drawings: {u['skipped']}")
    elif u:
        lines.append(f"real held-out drawings ({u['n']}): live {u['active_top5']:.1%} -> candidate {u['candidate_top5']:.1%} ({u['delta']:+.1%} Top-5)")
    lines.append("gate: " + ("PASSED" if report["passed"] else "FAILED"))
    return "\n".join(lines)


# ------------------------------------------------------------------------------------------------ the cycle

def run_cycle(cfg: Config, kaggle: Kaggle, run_dir: Path | None = None, log=print) -> dict:
    """Run (or resume) the cycle and return its state. Raises CycleError with advice when a safeguard stops it."""
    reg = registry.load(cfg.models_dir)
    live = reg["active"]
    if live is None:
        raise CycleError("no model is live yet: register and promote one first")
    run_dir = run_dir or (cfg.work_dir / datetime.now().strftime("%Y%m%d-%H%M%S"))
    run_dir.mkdir(parents=True, exist_ok=True)
    state_file = run_dir / "state.json"
    state = json.loads(state_file.read_text(encoding="utf-8")) if state_file.exists() else {"done": [], "live_at_start": live}
    if state["live_at_start"] != live and "install" not in state["done"]:
        raise CycleError(f"the live model changed from {state['live_at_start']} to {live} since this run started; start a new run")
    version = state.setdefault("version", next_version(cfg.models_dir))
    classes = json.loads((cfg.models_dir / live / "meta.json").read_text(encoding="utf-8"))["classes"]
    jsonl = run_dir / "training.jsonl"
    kernel_ref = kernel_id(kaggle.user, version)

    def step(name: str, fn) -> None:
        if name in state["done"]:
            log(f"[{name}] already done, skipping")
            return
        log(f"[{name}] ...")
        fn()
        state["done"].append(name)
        state_file.write_text(json.dumps(state, indent=2), encoding="utf-8")

    def export():
        n = (cfg.exporter or export_drawings)(cfg.database_url, jsonl)
        state["exported"] = n
        log(f"    {n} consented, label-confirmed drawings exported")

    def check():
        state["data"] = check_data(jsonl, classes, cfg.min_heldout)
        log(f"    {state['data']['train']} to train on, {state['data']['heldout']} held out, {state['data']['classes_covered']} classes, "
            f"pointers {state['data']['by_input_type']}")

    step("export", export)
    step("check", check)
    if cfg.dry_run:
        log("dry run: stopping before anything is sent to Kaggle")
        return state

    checkpoint = reg["versions"][live].get("checkpoint")
    if not checkpoint:
        raise CycleError(f"{live} has no recorded checkpoint: python -m src.flywheel.registry set-checkpoint {live} <kaggle kernel> <path to best.pt in its output>")

    step("data", lambda: kaggle.publish_dataset(stage_userdata(run_dir / "userdata", jsonl, kaggle.user), f"drawings for {version}"))
    step("code", kaggle.publish_code)

    def train():
        kaggle.push_kernel(stage_kernel(run_dir / "kernel", kaggle.user, version, checkpoint))
        started = time.time()
        deadline = started + cfg.timeout_seconds
        seen_active = False
        while True:
            status = kaggle.kernel_status(kernel_ref)
            log(f"    kernel: {status}")
            seen_active = seen_active or "RUNNING" in status or "QUEUED" in status
            if seen_active or time.time() - started > FIRST_LOOK_SECONDS:         # until then a final status may be the previous run's
                if "COMPLETE" in status:
                    return
                if "ERROR" in status or "CANCEL" in status:
                    raise CycleError(f"the Kaggle kernel ended with {status}; open https://www.kaggle.com/code/{kernel_ref} for its log, then --resume this run")
            if time.time() > deadline:
                raise CycleError("gave up waiting for the Kaggle kernel; --resume this run later")
            time.sleep(cfg.poll_seconds if seen_active else min(cfg.poll_seconds, 20))

    def download():
        kaggle.download_output(kernel_ref, run_dir / "output")
        out = run_dir / "output" / "out"
        missing = [p.format(v=version) for p in EXPECTED_OUTPUT if not (out / p.format(v=version)).exists()]
        if missing:
            raise CycleError(f"the kernel's output is incomplete (missing {', '.join(missing)}); check out/log.txt in {run_dir / 'output'}")
        failed = [s["step"] for s in json.loads((out / "steps.json").read_text(encoding="utf-8")) if s["exit"] != 0]
        if failed:
            raise CycleError(f"kernel steps failed: {', '.join(failed)} (see {out / 'log.txt'})")

    step("train", train)
    step("download", download)
    step("install", lambda: install_version(run_dir / "output", version, live, cfg.models_dir, cfg.results_dir, kernel_ref))

    def run_compare():
        report = compare(cfg.models_dir, version, live, cfg.heldout, jsonl, cfg.tolerance, cfg.min_heldout, cfg.per_class)
        cfg.results_dir.mkdir(parents=True, exist_ok=True)
        (cfg.results_dir / f"gate_{live}_to_{version}.json").write_text(json.dumps({"candidate": version, "active_before": live, "comparison": report}, indent=2),
                                                                          encoding="utf-8")
        state["gate_passed"] = report["passed"]
        state["summary"] = summarise(report)
        log(state["summary"].replace("\n", "\n    "))

    step("compare", run_compare)

    def decide():
        if not state["gate_passed"]:
            log(f"    {version} stays a candidate: the gate failed. Promote anyway only with: python -m src.flywheel.registry promote {version} --force ...")
            state["promoted"] = False
            return
        want = cfg.promote if cfg.promote is not None else (cfg.ask(f"Promote {version} (live now: {live})?") if cfg.ask else
                                                           (sys.stdin.isatty() and input(f"Promote {version} (live now: {live})? [y/N] ").strip().lower() == "y"))
        if not want:
            log(f"    not promoted. When ready: python -m src.flywheel.registry promote {version} --heldout {cfg.heldout} --user-eval {jsonl}")
            state["promoted"] = False
            return
        registry.promote(version, cfg.models_dir, heldout=cfg.heldout, user_eval=jsonl, tolerance=cfg.tolerance, min_user=cfg.min_heldout, per_class=cfg.per_class)
        state["promoted"] = True
        log(f"    {version} is live in the registry. To use it: npm run build:web (the web build ships only the live model), then restart the API "
            f"or POST /api/v1/admin/model/reload as an admin.")

    step("promote", decide)
    return state


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--database-url", help="the app's database (default: apps/api/prescribble.db)")
    ap.add_argument("--kaggle-user", default=Config.user)
    ap.add_argument("--min-heldout", type=int, default=Config.min_heldout)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--promote", dest="promote", action="store_true", default=None)
    ap.add_argument("--no-promote", dest="promote", action="store_false")
    ap.add_argument("--resume", type=Path)
    a = ap.parse_args(argv)
    cfg = Config(user=a.kaggle_user, min_heldout=a.min_heldout, promote=a.promote, dry_run=a.dry_run)
    if a.database_url:
        cfg.database_url = a.database_url
    try:
        state = run_cycle(cfg, Kaggle(a.kaggle_user), a.resume)
    except CycleError as e:
        print(f"stopped: {e}", file=sys.stderr)
        return 2
    print(json.dumps({k: v for k, v in state.items() if k in ("version", "exported", "data", "gate_passed", "promoted")}, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
