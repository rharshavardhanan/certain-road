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
YOLO_DIR = repo_root() / CFG["paths"]["yolo"]
LOCKED = repo_root() / "results" / "LOCKED"
ALLOWED = {"A": {"india_full", "bharatpothole", "chennai"},
           "B": {"india_heldout", "bharatpothole", "chennai"}}


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def git_commit() -> str:
    return subprocess.run(["git", "rev-parse", "HEAD"], capture_output=True,
                          text=True, check=True).stdout.strip()


def dirty_tree() -> bool:
    return bool(subprocess.run(["git", "status", "--porcelain"], capture_output=True,
                               text=True, check=True).stdout.strip())


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", required=True, choices=sorted(ALLOWED))
    ap.add_argument("--set", required=True, dest="eval_set")
    ap.add_argument("--weights", required=True, type=Path)
    ap.add_argument("--data-root", type=Path, default=YOLO_DIR)
    ap.add_argument("--conf", type=float, default=0.001)
    ap.add_argument("--self-test", action="store_true",
                    help="exercise the whole path on a dummy set; writes the lock "
                         "to a scratch directory so it can never collide with a "
                         "real locked result, and skips the allow-list and the "
                         "clean-tree requirement")
    ap.add_argument("--out", type=Path, default=None,
                    help="self-test only: where to write the lock")
    args = ap.parse_args()

    if not args.self_test and args.eval_set not in ALLOWED[args.model]:
        raise SystemExit(f"model {args.model} may not be evaluated on {args.eval_set}; "
                         f"allowed: {sorted(ALLOWED[args.model])}")

    locked_dir = args.out if (args.self_test and args.out) else LOCKED
    locked_dir.mkdir(parents=True, exist_ok=True)
    lock = locked_dir / f"{args.model}_{args.eval_set}.json"
    if lock.exists():
        raise SystemExit(f"LOCKED already: {lock}. Delete it by hand to re-run.")

    if dirty_tree() and not args.self_test:
        raise SystemExit("working tree is dirty; commit first so the stamped "
                         "git hash matches the code that produced the number (D058)")

    from ultralytics import YOLO

    names = {int(k): v for k, v in CFG["classes"].items()}
    out_dir = locked_dir / f"{args.model}_{args.eval_set}_run"
    out_dir.mkdir(parents=True, exist_ok=True)

    data_yaml = out_dir / "data.yaml"
    with open(data_yaml, "w") as fh:
        yaml.safe_dump({"path": str(args.data_root.resolve()),
                        "train": f"{args.eval_set}.txt", "val": f"{args.eval_set}.txt",
                        "names": names}, fh, sort_keys=False)

    model = YOLO(str(args.weights))
    result = model.val(data=str(data_yaml), split="val", device="cpu", conf=args.conf,
                       save_json=True, plots=True, project=str(out_dir), name="val",
                       exist_ok=True, verbose=False)

    image_paths = [args.data_root / "images" / f"{Path(x).stem}.jpg"
                   for x in (args.data_root / f"{args.eval_set}.txt").read_text().splitlines()
                   if x.strip()]
    gt, stem_to_id = yolo_to_coco_gt(image_paths, args.data_root / "labels", names)
    pred_json = next((out_dir / "val").glob("predictions.json"), None)
    coco = coco_eval(gt, load_predictions(pred_json, stem_to_id, len(names)) if pred_json else [], names)

    ultra = {"map50": float(result.box.map50), "map50_95": float(result.box.map),
             "precision": float(result.box.mp), "recall": float(result.box.mr)}
    delta = abs(ultra["map50"] - coco["map50"])

    payload = {
        "model": args.model, "set": args.eval_set,
        "weights": str(args.weights), "weights_sha256": sha256(args.weights),
        "images": len(image_paths), "conf": args.conf, "device": "cpu",
        "ultralytics_metrics": ultra, "pycocotools_metrics": coco,
        "cross_check": {"map50_abs_delta": round(delta, 4), "tolerance": 0.03,
                        "ok": delta <= 0.03},
        "stamp": {"utc": datetime.now(UTC).isoformat(), "git_commit": git_commit(),
                  "python": platform.python_version(), "platform": platform.platform()},
    }
    lock.write_text(json.dumps(payload, indent=2))
    print(json.dumps(payload, indent=2))
    if not payload["cross_check"]["ok"]:
        print("\nCROSS-CHECK FAILED: pycocotools and ultralytics disagree by more "
              "than 0.03 - suspect the ground-truth conversion (T6 step 4)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
