"""T5/T7 — one training script for Kaggle, driven entirely by job.json.

Everything that varies between runs — Model A vs B, smoke vs full, fresh vs
resume — is data in `job.json`, not a code edit. That keeps the script that
produced Model A byte-identical to the one that produced Model B, so a difference
in results cannot be a difference in code.

Several Kaggle-specific hazards are handled explicitly:

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
COCO weights. Kaggle's image does **not** ship ultralytics either — assuming it
did cost a third smoke run. So both the wheels and the COCO weights travel as an
attached dataset and are installed with `--no-index`. The version that actually
ran is recorded in `status.json`, because a silently different ultralytics is a
silently different experiment.

**A dataset version can land partially.** One did: 8,000 labels arrived and zero
images, so ultralytics called all 9,689 pairs corrupt and a GPU session bought
nothing. `preflight_dataset` re-asks that question where it can actually be
answered — on the mount, against the lists the trainer reads — because Kaggle's
`datasets files` endpoint paginates and cannot.

**The job is embedded, not shipped alongside.** Kaggle uploads only the file named
by `code_file` — a sibling `job.json` simply does not arrive, which is how the
first smoke run died. `kaggle_push.py` rewrites `EMBEDDED_JOB` in a copy of this
file before pushing; the `job.json` fallback exists so the script still runs
locally.
"""

import glob
import json
import os
import shutil
import subprocess
import sys
from multiprocessing.pool import ThreadPool
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
    """Install the pinned ultralytics, preferring attached wheels over the network.

    Order matters. Offline wheels come first because they are the only path that
    works without a phone-verified account, and `--no-deps` is essential: letting
    pip resolve ultralytics' dependency tree would pull its own torch and replace
    the CUDA-matched build Kaggle ships, which is the exact failure that would
    have destroyed the Colab run.
    """
    try:
        import ultralytics
        if ultralytics.__version__ == pin:
            print(f"ultralytics {pin} already present", flush=True)
            return pin
        preinstalled: str | None = ultralytics.__version__
    except ImportError:
        preinstalled = None

    wheels = sorted(glob.glob("/kaggle/input/**/*.whl", recursive=True))
    if wheels:
        print(f"installing {len(wheels)} attached wheel(s) offline", flush=True)
        offline = subprocess.run(
            [sys.executable, "-m", "pip", "install", "-q", "--no-index", "--no-deps", *wheels],
            capture_output=True, text=True)
        if offline.returncode != 0:
            print(f"offline install failed: {offline.stderr.strip()[-400:]}", flush=True)
    else:
        print("no wheels attached; trying the network", flush=True)
        online = subprocess.run(
            [sys.executable, "-m", "pip", "install", "-q", f"ultralytics=={pin}"],
            capture_output=True, text=True)
        if online.returncode != 0:
            print(f"pip install failed (no kernel internet?): "
                  f"{online.stderr.strip()[-300:]}", flush=True)

    try:
        import importlib

        import ultralytics as u
        importlib.reload(u)
        return u.__version__
    except ImportError as exc:
        raise SystemExit(
            f"ultralytics unavailable: no network, no wheels that installed, and "
            f"the image ships none (preinstalled={preinstalled})"
        ) from exc


def resolve_init_weights(name: str) -> str:
    """Prefer an attached dataset copy over a name ultralytics would download."""
    # Match the whole suffix, not just the basename: several attached datasets can
    # contain a `best.pt`, and picking the wrong one would train Model B from the
    # wrong parent without any error.
    hits = glob.glob(f"/kaggle/input/**/{name}", recursive=True)
    if not hits and "/" in name:
        hits = glob.glob(f"/kaggle/input/**/{Path(name).name}", recursive=True)
    if hits:
        print(f"init weights from dataset: {hits[0]}", flush=True)
        return sorted(hits)[0]
    print(f"init weights: {name} (ultralytics will resolve or download)", flush=True)
    return name


def find_dataset_root(anchor: str = ANCHOR) -> Path:
    hits = glob.glob(f"/kaggle/input/**/{anchor}", recursive=True)
    if not hits:
        raise FileNotFoundError(f"no {anchor} under /kaggle/input - is the dataset attached?")
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


def assert_no_forbidden_prefix(root: Path, job: dict) -> None:
    """Refuse to train if a forbidden prefix appears in any training list.

    Model A's entire claim is that it never saw India. The split tests assert
    that locally, but they run against the repo — not against the file the kernel
    actually reads after an upload, a dataset version bump or a hand-edited yaml.
    This is the last check before the optimiser sees a single image, and it costs
    milliseconds against a six-hour run producing a number that would have to be
    thrown away.
    """
    forbidden = job.get("forbid_prefixes") or []
    if not forbidden:
        return
    lists = job["train"] if isinstance(job["train"], list) else [job["train"]]
    for name in lists:
        entries = (root / name).read_text().splitlines()
        hits = [e for e in entries
                if any(Path(e).name.startswith(p) for p in forbidden)]
        if hits:
            raise SystemExit(
                f"REFUSING TO TRAIN: {name} contains {len(hits)} forbidden "
                f"entries (prefixes {forbidden}); first: {hits[:3]}")
        print(f"guard ok: {name} has 0 of {forbidden} in {len(entries)} entries", flush=True)


def preflight_dataset(root: Path, job: dict) -> dict:
    """Prove every listed image and label is on the mount before the run starts.

    A dataset version can land partially. One did: 8,000 labels arrived, zero
    images, and ultralytics dutifully scanned 9,689 entries, called every one
    corrupt, and spent a GPU session producing nothing. The readiness check
    written after that asked Kaggle's `datasets files` endpoint instead, which
    **paginates** — a file on page two reads as absent and a lucky prefix on
    page one reads as present however few of its members arrived. It answers a
    question about an API listing when the question is about the bytes the
    trainer will open. Only the kernel can answer that, after the mount
    resolves, against the same list files the trainer reads.

    Label paths come from ultralytics' own `img2label_paths`. Deriving them here
    would let the pre-flight pass while the trainer still finds nothing, which
    is worse than no pre-flight: it turns a loud failure into a confident one.

    Two passes, cheapest first. Existence is a second over 11k paths and catches
    the failure actually observed; the ultralytics scan decodes every image and
    catches truncation. **Empty label files are not an error** — most images in
    a pothole pool carry no box (india_train is 4,622 images and 2,025 boxes),
    and ultralytics counts those `ne`, not `nm`. Aborting on `ne` would refuse
    every correctly-built pool.
    """
    from ultralytics.data.utils import img2label_paths, verify_image_label

    def as_list(value) -> list[str]:
        return value if isinstance(value, list) else [value]

    named = ([("train", n) for n in as_list(job["train"])]
             + [("val", n) for n in as_list(job["val"])])
    num_cls = len(job["names"])

    report: dict[str, dict] = {}
    pairs: list[tuple[str, str]] = []
    for role, name in named:
        entries = [e.strip() for e in (root / name).read_text().splitlines() if e.strip()]
        images = [os.path.normpath(str(root / e)) for e in entries]
        labels = img2label_paths(images)
        found_i = sum(1 for p in images if os.path.isfile(p))
        found_l = sum(1 for p in labels if os.path.isfile(p))
        report[name] = {"role": role, "listed": len(entries),
                        "images_present": found_i, "labels_present": found_l}
        print(f"preflight {role} {name}: {found_i}/{len(entries)} images, "
              f"{found_l}/{len(entries)} labels", flush=True)
        if found_i < len(entries) or found_l < len(entries):
            raise SystemExit(
                f"REFUSING TO TRAIN: {name} lists {len(entries)} entries but the "
                f"mount has {found_i} images and {found_l} labels "
                f"(root {root}). The dataset version is incomplete.")
        pairs += list(zip(images, labels, strict=True))

    nm = ne = nc = 0
    msgs: list[str] = []
    args = [(im, lb, "", False, num_cls, 0, 0, False) for im, lb in pairs]
    with ThreadPool(min(8, os.cpu_count() or 1)) as pool:
        for out in pool.imap_unordered(verify_image_label, args):
            nm, ne, nc = nm + out[5], ne + out[7], nc + out[8]
            if out[9]:
                msgs.append(out[9])
    print(f"preflight scan: {len(pairs)} pairs, missing={nm} empty={ne} "
          f"corrupt={nc}", flush=True)
    report["scan"] = {"pairs": len(pairs), "missing": nm, "empty": ne, "corrupt": nc}
    if nm or nc:
        raise SystemExit(
            f"REFUSING TO TRAIN: ultralytics scan of {len(pairs)} pairs reports "
            f"{nm} missing and {nc} corrupt; first: {msgs[:3]}")
    return report


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

    root = find_dataset_root(job.get("anchor", ANCHOR))
    data_yaml = write_data_yaml(root, job)
    assert_no_forbidden_prefix(root, job)
    preflight_dataset(root, job)
    device = list(range(torch.cuda.device_count())) or "cpu"
    print(f"device: {device}", flush=True)

    cfg = dict(job["train_cfg"])
    resume_from = find_resume_checkpoint(job["run"]) if job.get("resume") else None
    if resume_from:
        print(f"RESUMING from {resume_from}", flush=True)
        model = YOLO(resume_from)
        outcome = model.train(resume=True)
    else:
        model = YOLO(resolve_init_weights(job["init_weights"]))
        outcome = model.train(
            data=str(data_yaml), device=device,
            project=str(WORKING / "runs"), name=job["run"], exist_ok=True, **cfg
        )

    # `train()` returns a dict under DDP in this ultralytics version, not an
    # object with `.save_dir` — reading it off the return value cost a smoke run
    # *after* training had already succeeded. The trainer always knows.
    results_dir = Path(
        getattr(outcome, "save_dir", None)
        or (outcome.get("save_dir") if isinstance(outcome, dict) else None)
        or model.trainer.save_dir
    )
    print(f"results_dir: {results_dir}", flush=True)

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
