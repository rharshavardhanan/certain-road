"""T5 — build and push a Kaggle training kernel.

Refuses to push while the kernel is queued or running, because pushing over a
live run silently discards it — the failure mode that costs a GPU-hour and looks
like nothing happened.
"""

import json
import shutil
import subprocess
import sys
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from certain_road.core.paths import repo_root  # noqa: E402

CFG = yaml.safe_load((repo_root() / "configs" / "project.yaml").read_text())
KAGGLE_USER = CFG["kaggle"]["username"]
DATASET = f"{KAGGLE_USER}/{CFG['kaggle']['dataset_slug']}"
WEIGHTS_DATASET = f"{KAGGLE_USER}/roadsight-weights"
BUILD = repo_root() / "kaggle" / "build"
ULTRALYTICS_PIN = "8.4.115"


def kernel_status(slug: str) -> str:
    out = subprocess.run(["kaggle", "kernels", "status", slug],
                         capture_output=True, text=True)
    return (out.stdout + out.stderr).strip()


def build(job: dict, slug: str, kernel_sources: list[str]) -> Path:
    target = BUILD / slug
    if target.exists():
        shutil.rmtree(target)
    target.mkdir(parents=True)
    # Kaggle uploads only `code_file`; a sibling job.json never arrives, which
    # killed the first smoke run. Embed the job in the script itself.
    source = (repo_root() / "kaggle" / "train" / "train.py").read_text()
    marker = "EMBEDDED_JOB: dict | None = None"
    if marker not in source:
        raise SystemExit("train.py lost its EMBEDDED_JOB marker")
    source = source.replace(marker, f"EMBEDDED_JOB: dict | None = {job!r}")
    (target / "train.py").write_text(source)
    (target / "job.json").write_text(json.dumps(job, indent=2))  # local reference only
    (target / "kernel-metadata.json").write_text(json.dumps({
        "id": f"{KAGGLE_USER}/{slug}", "title": slug,
        "code_file": "train.py", "language": "python", "kernel_type": "script",
        "is_private": True, "enable_gpu": True, "enable_internet": True,
        "dataset_sources": [DATASET, WEIGHTS_DATASET], "kernel_sources": kernel_sources,
        "competition_sources": [],
    }, indent=2))
    return target


def job_for(kind: str) -> tuple[str, dict]:
    names = {str(k): v for k, v in CFG["classes"].items()}
    if kind == "smoke":
        cfg = dict(CFG["train_A"])
        cfg.pop("model")
        cfg.update(epochs=1, fraction=0.05, save_period=-1)
        return "roadsight-train-a-smoke", {
            "run": "smoke", "init_weights": CFG["train_A"]["model"],
            "train": "nonindia_train.txt", "val": "nonindia_val.txt",
            "names": names, "train_cfg": cfg, "resume": False,
            "forbid_prefixes": ["India__"],
            "ultralytics": ULTRALYTICS_PIN,
        }
    if kind == "a":
        cfg = dict(CFG["train_A"])
        cfg.pop("model")
        return "roadsight-train-a", {
            "run": "model_a", "init_weights": CFG["train_A"]["model"],
            "train": "nonindia_train.txt", "val": "nonindia_val.txt",
            "names": names, "train_cfg": cfg, "resume": False,
            # Model A's whole claim is that it never saw India (D055).
            "forbid_prefixes": ["India__"],
            "ultralytics": ULTRALYTICS_PIN,
        }
    raise SystemExit(f"unknown job kind {kind!r}")


def main() -> int:
    kind = sys.argv[1] if len(sys.argv) > 1 else "smoke"
    sources = sys.argv[2:]
    slug, job = job_for(kind)

    status = kernel_status(f"{KAGGLE_USER}/{slug}")
    if any(word in status.lower() for word in ("running", "queued")):
        raise SystemExit(f"refusing to push: {slug} is {status}")

    target = build(job, slug, sources)
    print(f"built {target}\n{json.dumps(job, indent=2)}", flush=True)
    result = subprocess.run(["kaggle", "kernels", "push", "-p", str(target)],
                            capture_output=True, text=True)
    print(result.stdout or result.stderr, flush=True)
    print(f"\nwatch: kaggle kernels status {KAGGLE_USER}/{slug}")
    return result.returncode


if __name__ == "__main__":
    raise SystemExit(main())
