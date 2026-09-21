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
"""

import glob
import json
import shutil
import subprocess
import sys
from pathlib import Path

WORKING = Path("/kaggle/working")
ANCHOR = "nonindia_train.txt"


def log_environment() -> dict:
    print("=" * 70, flush=True)
    subprocess.run(["nvidia-smi"], check=False)
    import torch

    info = {"torch": torch.__version__, "cuda": torch.version.cuda,
            "gpus": torch.cuda.device_count(),
            "names": [torch.cuda.get_device_name(i) for i in range(torch.cuda.device_count())]}
    print(json.dumps(info, indent=2), flush=True)
    return info


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
    job = json.loads(Path(__file__).with_name("job.json").read_text())
    print(json.dumps(job, indent=2), flush=True)

    subprocess.run([sys.executable, "-m", "pip", "install", "-q",
                    f"ultralytics=={job['ultralytics']}", "pycocotools"], check=True)

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
        model = YOLO(job["init_weights"])
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
    }, indent=2))
    print(json.dumps(json.loads((export / "status.json").read_text()), indent=2), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
