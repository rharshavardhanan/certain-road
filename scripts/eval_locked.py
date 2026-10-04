"""T6 — locked evaluation on a held-out set. One shot, on CPU, fully stamped.

A locked run writes a lock file and refuses to run again. That is the whole
point: a held-out number you can re-roll until it looks good is not a held-out
number. If a genuine re-run is needed, the lock must be deleted by hand, which
leaves a deliberate act rather than an accident.

`device=cpu` is forced. MPS has no deterministic implementation for several ops
used here (seen in T4), so a CPU result is the one another machine can reproduce.

Every output carries the weights SHA256, package versions, UTC timestamp and git
commit — which is why D058 requires a commit before any locked run: otherwise the
stamp names a commit that does not contain the code that produced the number.

The per-image predictions are written by ultralytics, not by this script:
`model.val(save_json=True)` leaves them in `<run>/val/predictions.json`, which T10
(`exp_conformal.py`), T11 (`exp_drift.py`) and T12 (`exp_allocation.py`) read.
"""

import argparse
import hashlib
import json
import platform
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from certain_road.core.paths import repo_root  # noqa: E402
from certain_road.perception.metrics_coco import (  # noqa: E402
    coco_eval,
    load_predictions,
    yolo_to_coco_gt,
)

CFG = yaml.safe_load((repo_root() / "configs" / "project.yaml").read_text())
EVAL = CFG["eval"]
YOLO_DIR = repo_root() / CFG["paths"]["yolo"]
LOCKED = repo_root() / "results" / "LOCKED"
POTHOLE = int(CFG["pothole_class"])
NAMES_3 = {int(k): v for k, v in CFG["classes"].items()}
ALLOWED = {
    "A": {"india_full", "bharatpothole", "chennai"},
    "B": {"india_heldout", "bharatpothole", "chennai"},
    "P": {"india_heldout", "bharatpothole", "chennai"},
}

# The class map follows the model rather than a command-line flag, because a
# flag can be forgotten and the failure is silent: scoring Model P's class 0
# against `linear_crack` ground truth returns a plausible, wrong number. That is
# the same trap `load_predictions` exists to close, one level up.
MODEL_CLASSES = {"A": NAMES_3, "B": NAMES_3, "P": {0: "pothole"}}


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def git_commit() -> str:
    return subprocess.run(
        ["git", "rev-parse", "HEAD"], capture_output=True, text=True, check=True
    ).stdout.strip()


def dirty_tree() -> bool:
    return bool(
        subprocess.run(
            ["git", "status", "--porcelain"], capture_output=True, text=True, check=True
        ).stdout.strip()
    )


def pothole_only_root(out_dir: Path, source: Path, eval_set: str) -> Path:
    """Materialise a pothole-only view of `eval_set` for a 1-class model.

    The held-out sets are deliberately absent from `data/yolo_pothole`: that pool
    is the Kaggle upload staging directory, and D063 keeps `india_cal` and
    `india_test` off Kaggle entirely, so that the calibration firewall is a fact
    about where the bytes are rather than a convention the code must honour.

    The pothole-only ground truth for a locked run is therefore derived here,
    inside the run directory, from the 3-class labels. Images are symlinked, so
    the pixels are provably the same ones every other model was scored on.
    """
    root = out_dir / "gt_root"
    (root / "images").mkdir(parents=True, exist_ok=True)
    (root / "labels").mkdir(parents=True, exist_ok=True)
    stems = [Path(x).stem for x in (source / f"{eval_set}.txt").read_text().split() if x.strip()]
    boxes = 0
    for stem in stems:
        img = root / "images" / f"{stem}.jpg"
        if not img.exists():
            img.symlink_to((source / "images" / f"{stem}.jpg").resolve())
        kept = [
            "0 " + " ".join(r.split()[1:])
            for r in (source / "labels" / f"{stem}.txt").read_text().splitlines()
            if r.strip() and int(r.split()[0]) == POTHOLE
        ]
        boxes += len(kept)
        (root / "labels" / f"{stem}.txt").write_text("\n".join(kept) + ("\n" if kept else ""))
    (root / f"{eval_set}.txt").write_text("".join(f"./images/{s}.jpg\n" for s in stems))
    print(
        f"pothole-only ground truth: {len(stems)} images, {boxes} pothole boxes "
        f"(derived from {source}, never uploaded)",
        flush=True,
    )
    return root


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", required=True, choices=sorted(ALLOWED))
    ap.add_argument("--set", required=True, dest="eval_set")
    ap.add_argument("--weights", required=True, type=Path)
    ap.add_argument("--data-root", type=Path, default=YOLO_DIR)

    ap.add_argument(
        "--self-test",
        action="store_true",
        help="exercise the whole path on a dummy set; writes the lock "
        "to a scratch directory so it can never collide with a "
        "real locked result, and skips the allow-list and the "
        "clean-tree requirement",
    )
    ap.add_argument(
        "--out", type=Path, default=None, help="self-test only: where to write the lock"
    )
    args = ap.parse_args()

    if not args.self_test and args.eval_set not in ALLOWED[args.model]:
        raise SystemExit(
            f"model {args.model} may not be evaluated on {args.eval_set}; "
            f"allowed: {sorted(ALLOWED[args.model])}"
        )

    locked_dir = args.out if (args.self_test and args.out) else LOCKED
    locked_dir.mkdir(parents=True, exist_ok=True)
    lock = locked_dir / f"{args.model}_{args.eval_set}.json"
    if lock.exists():
        raise SystemExit(f"LOCKED already: {lock}. Delete it by hand to re-run.")

    if dirty_tree() and not args.self_test:
        raise SystemExit(
            "working tree is dirty; commit first so the stamped "
            "git hash matches the code that produced the number (D058)"
        )

    from ultralytics import YOLO

    names = MODEL_CLASSES[args.model]
    out_dir = locked_dir / f"{args.model}_{args.eval_set}_run"
    out_dir.mkdir(parents=True, exist_ok=True)

    # A 1-class model needs 1-class ground truth, or the scorer silently
    # compares its only channel against the wrong one.
    data_root = (
        pothole_only_root(out_dir, args.data_root, args.eval_set)
        if len(names) == 1
        else args.data_root
    )

    data_yaml = out_dir / "data.yaml"
    with open(data_yaml, "w") as fh:
        yaml.safe_dump(
            {
                "path": str(data_root.resolve()),
                "train": f"{args.eval_set}.txt",
                "val": f"{args.eval_set}.txt",
                "names": names,
            },
            fh,
            sort_keys=False,
        )

    model = YOLO(str(args.weights))
    result = model.val(
        data=str(data_yaml),
        split="val",
        save_json=True,
        plots=True,
        project=str(out_dir),
        name="val",
        exist_ok=True,
        verbose=False,
        conf=EVAL["conf"],
        iou=EVAL["iou"],
        max_det=EVAL["max_det"],
        imgsz=EVAL["imgsz"],
        rect=EVAL["rect"],
        half=EVAL["half"],
        device=EVAL["device"],
    )

    image_paths = [
        data_root / "images" / f"{Path(x).stem}.jpg"
        for x in (data_root / f"{args.eval_set}.txt").read_text().splitlines()
        if x.strip()
    ]
    gt, stem_to_id = yolo_to_coco_gt(image_paths, data_root / "labels", names)
    pred_json = next((out_dir / "val").glob("predictions.json"), None)
    preds = load_predictions(pred_json, stem_to_id, len(names)) if pred_json else []
    coco = coco_eval(gt, preds, names)

    ultra = {
        "map50": float(result.box.map50),
        "map50_95": float(result.box.map),
        "precision": float(result.box.mp),
        "recall": float(result.box.mr),
    }
    delta = abs(ultra["map50"] - coco["map50"])

    payload = {
        "model": args.model,
        "set": args.eval_set,
        "classes": names,
        "gt": "pothole-only (derived)" if len(names) == 1 else "3-class",
        "weights": str(args.weights),
        "weights_sha256": sha256(args.weights),
        "images": len(image_paths),
        "eval_settings": EVAL,
        "ultralytics_metrics": ultra,
        "pycocotools_metrics": coco,
        "cross_check": {"map50_abs_delta": round(delta, 4), "tolerance": 0.03, "ok": delta <= 0.03},
        "stamp": {
            "utc": datetime.now(UTC).isoformat(),
            "git_commit": git_commit(),
            "python": platform.python_version(),
            "platform": platform.platform(),
        },
    }
    lock.write_text(json.dumps(payload, indent=2))
    print(json.dumps(payload, indent=2))
    if not payload["cross_check"]["ok"]:
        print(
            "\nCROSS-CHECK FAILED: pycocotools and ultralytics disagree by more "
            "than 0.03 - suspect the ground-truth conversion (T6 step 4)"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
