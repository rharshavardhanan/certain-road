"""T5/T7 — one training script for Kaggle, driven entirely by job.json.

Everything that varies between runs — Model A vs B, smoke vs full, fresh vs
resume — is data in `job.json`, not a code edit. That keeps the script that
produced Model A byte-identical to the one that produced Model B, so a difference
in results cannot be a difference in code.

Three Kaggle-specific hazards are handled explicitly:

**The mount path varies.** `/kaggle/input/<slug>/` is not stable across dataset
versions or attachments, so the root is found by globbing for a file we know is
in it rather than hardcoded.

**Only ultralytics and pycocotools are installed** (D056). Kaggle images ship
torch built against their own CUDA; installing a full requirements set on top
replaces a working GPU stack with a generic one. That is exactly what would have
destroyed the Colab run.

**`optimizer` is pinned, never `auto`** (D043). Ultralytics' `optimizer: auto`
silently discards the configured `lr0` and substitutes its own heuristic. The
resolved optimizer line is echoed so the log proves which was used.

**Nothing is downloaded at runtime.** Kernel internet requires a phone-verified
Kaggle account; without it pip cannot reach PyPI *and* ultralytics cannot fetch
COCO weights, which is how the second smoke run died. So the pinned ultralytics
is used only if already present, and init weights are resolved from an attached
dataset rather than a URL. The version that actually ran is recorded in
`status.json`, because a silently different ultralytics is a silently different
experiment.

**The job is embedded, not shipped alongside.** Kaggle uploads only the file named
by `code_file` — a sibling `job.json` simply does not arrive, which is how the
first smoke run died. `kaggle_push.py` rewrites `EMBEDDED_JOB` in a copy of this
file before pushing; the `job.json` fallback exists so the script still runs
locally.
"""

import glob
import json
import shutil
import subprocess
import sys
from pathlib import Path

WORKING = Path("/kaggle/working")
ANCHOR = "nonindia_train.txt"

# Replaced literally by kaggle_push.py. Kaggle ships one file, so the job must
# travel inside it.
EMBEDDED_JOB: dict | None = None


def load_job() -> dict:
    if EMBEDDED_JOB is not None:
        return EMBEDDED_JOB
    return json.loads(Path(__file__).with_name("job.json").read_text())


def log_environment() -> dict:
    print("=" * 70, flush=True)
    subprocess.run(["nvidia-smi"], check=False)
    import torch

    info = {"torch": torch.__version__, "cuda": torch.version.cuda,
            "gpus": torch.cuda.device_count(),
            "names": [torch.cuda.get_device_name(i) for i in range(torch.cuda.device_count())]}
    print(json.dumps(info, indent=2), flush=True)
    return info


def ensure_ultralytics(pin: str) -> str:
    """Install the pin if the network allows; otherwise use what the image ships.

    Failing hard here would be wrong: Kaggle's image already carries a working
    ultralytics built against its own CUDA, and the run is more valuable than the
    exact patch version. What is not acceptable is *not knowing*, so the version
    actually imported is returned and recorded.
    """
    try:
        import ultralytics
        if ultralytics.__version__ == pin:
            print(f"ultralytics {pin} already present", flush=True)
            return pin
    except ImportError:
        ultralytics = None

    result = subprocess.run(
        [sys.executable, "-m", "pip", "install", "-q", f"ultralytics=={pin}", "pycocotools"],
        capture_output=True, text=True)
    if result.returncode != 0:
        print(f"pip install failed (no kernel internet?): {result.stderr.strip()[-300:]}",
              flush=True)
        if ultralytics is None:
            raise SystemExit("ultralytics is neither installed nor installable")
        print(f"CONTINUING with preinstalled ultralytics {ultralytics.__version__} "
              f"(wanted {pin})", flush=True)
        return ultralytics.__version__

    import importlib

    import ultralytics as u
    importlib.reload(u)
    return u.__version__


def resolve_init_weights(name: str) -> str:
    """Prefer an attached dataset copy over a name ultralytics would download."""
    hits = glob.glob(f"/kaggle/input/**/{Path(name).name}", recursive=True)
    if hits:
        print(f"init weights from dataset: {hits[0]}", flush=True)
        return sorted(hits)[0]
    print(f"init weights: {name} (ultralytics will resolve or download)", flush=True)
    return name


def find_dataset_root() -> Path:
    hits = glob.glob(f"/kaggle/input/**/{ANCHOR}", recursive=True)
    if not hits:
        raise FileNotFoundError(f"no {ANCHOR} under /kaggle/input - is the dataset attached?")
    root = Path(sorted(hits)[0]).parent
    print(f"dataset root: {root}", flush=True)
    return root


def write_data_yaml(root: Path, job: dict) -> Path:
    import yaml

    cfg = {"path": str(root), "train": job["train"], "val": job["val"],
           "names": {int(k): v for k, v in job["names"].items()}}
    out = WORKING / f"data_{job['run']}.yaml"
    with open(out, "w") as fh:
        yaml.safe_dump(cfg, fh, sort_keys=False)
    print(out.read_text(), flush=True)
    return out


def find_resume_checkpoint(run: str) -> str | None:
    hits = glob.glob(f"/kaggle/input/**/{run}/weights/last.pt", recursive=True)
    return sorted(hits)[0] if hits else None


def main() -> int:
    job = load_job()
    print(json.dumps(job, indent=2), flush=True)

    ultra_version = ensure_ultralytics(job["ultralytics"])

    env = log_environment()
    import torch
    from ultralytics import YOLO

    root = find_dataset_root()
    data_yaml = write_data_yaml(root, job)
    device = list(range(torch.cuda.device_count())) or "cpu"
    print(f"device: {device}", flush=True)

    cfg = dict(job["train_cfg"])
    resume_from = find_resume_checkpoint(job["run"]) if job.get("resume") else None
    if resume_from:
        print(f"RESUMING from {resume_from}", flush=True)
        model = YOLO(resume_from)
        results_dir = Path(model.train(resume=True).save_dir)
    else:
        model = YOLO(resolve_init_weights(job["init_weights"]))
        results_dir = Path(model.train(
            data=str(data_yaml), device=device,
            project=str(WORKING / "runs"), name=job["run"], exist_ok=True, **cfg
        ).save_dir)

    export = WORKING / "export" / job["run"]
    export.mkdir(parents=True, exist_ok=True)
    for pattern in ("weights/best.pt", "weights/last.pt", "results.csv", "args.yaml", "*.png"):
        for src in results_dir.glob(pattern):
            shutil.copy(src, export / src.name)

    finished = (results_dir / "weights" / "best.pt").exists()
    epochs_done = 0
    csv = results_dir / "results.csv"
    if csv.exists():
        epochs_done = max(0, len(csv.read_text().strip().splitlines()) - 1)
    (export / "status.json").write_text(json.dumps({
        "run": job["run"], "epochs_done": epochs_done,
        "epochs_requested": cfg.get("epochs"),
        "early_stopped": finished and epochs_done < int(cfg.get("epochs", 0)),
        "finished": finished, "environment": env,
        "ultralytics_used": ultra_version, "ultralytics_requested": job["ultralytics"],
    }, indent=2))
    print(json.dumps(json.loads((export / "status.json").read_text()), indent=2), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
