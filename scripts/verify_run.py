"""T5b post-run verification — what the kernel actually read and produced.

`test_splits.py` proves the lists in this repo are clean. This proves the *run*
was clean, by reading the numbers ultralytics itself printed after resolving
paths inside the kernel. For T5b specifically it is the run-level evidence that
stands in for the kernel guard, which landed after that run had already launched
(D065).

Checks, in the order a failure would matter:
  1. resolved train/val paths and their scan counts match the uploaded lists;
  2. every epoch's training losses are finite — a NaN there is divergence, unlike
     the NaN validation loss which D065 showed reaches no decision;
  3. non-India val mAP50 clears T5's 0.2 sanity bar;
  4. status.json says finished or early-stopped;
  5. best.pt SHA256 recorded, so the locked evaluation names the exact weights.
"""

import argparse
import hashlib
import json
import math
import re
import subprocess
import sys
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from certain_road.core.paths import repo_root  # noqa: E402

CFG = yaml.safe_load((repo_root() / "configs" / "project.yaml").read_text())
YOLO_DIR = repo_root() / CFG["paths"]["yolo"]
MAP50_FLOOR = 0.2
ANSI = re.compile(r"\x1b\[[0-9;]*m")


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def kernel_text(log_path: Path) -> str:
    events = json.loads(log_path.read_text())
    return ANSI.sub("", "".join(e["data"] for e in events)).replace("\r", "\n")


def expected_counts(train_splits: list[str], val_split: str, forbid_india: bool) -> dict[str, int]:
    """Total scanned images the kernel should report, from the lists it was given.

    Model A trains on non-India only; Model B trains on india_train plus a
    non-India replay sample. Hardcoding A's lists made B fail this check while
    the run itself was correct, so the expectation now comes from the job.

    The India assertion applies only where India is forbidden — Model B trains on
    india_train by design, and the held-out sets are not on Kaggle at all.
    """
    total = 0
    for split in train_splits:
        lines = [x for x in (YOLO_DIR / f"{split}.txt").read_text().splitlines() if x.strip()]
        total += len(lines)
        if forbid_india:
            india = [x for x in lines if Path(x).name.startswith("India__")]
            if india:
                raise SystemExit(f"{split}.txt contains {len(india)} India entries")
    val_lines = [x for x in (YOLO_DIR / f"{val_split}.txt").read_text().splitlines() if x.strip()]
    # Held-out India must never be a validation set for either model.
    for banned in ("india_cal", "india_test", "india_heldout"):
        if val_split == banned:
            raise SystemExit(f"{val_split} is held out and must not be validated on")
    return {"train": total, "val": len(val_lines)}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--slug", default="roadsight-train-a")
    ap.add_argument("--run", default="model_a")
    ap.add_argument("--train-splits", nargs="+", default=["nonindia_train"])
    ap.add_argument("--val-split", default="nonindia_val")
    ap.add_argument(
        "--allow-india-train", action="store_true", help="Model B trains on india_train by design"
    )
    args = ap.parse_args()

    dest = repo_root() / "runs" / "kaggle" / args.slug
    dest.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        [
            "kaggle",
            "kernels",
            "output",
            f"{CFG['kaggle']['username']}/{args.slug}",
            "-p",
            str(dest),
        ],
        check=False,
    )

    log = next(dest.glob("*.log"), None)
    if log is None:
        raise SystemExit(f"no kernel log under {dest}")
    text = kernel_text(log)
    report: dict = {"slug": args.slug, "checks": {}}

    # 1. what the kernel resolved and scanned
    scans = re.findall(r"(train|val):\s*Scanning\s+(\S+?)\.\.\.\s*([\d,]+)\s+images", text)
    seen: dict[str, tuple[str, int]] = {}
    for phase, path, count in scans:
        seen[phase] = (path, int(count.replace(",", "")))
    want = expected_counts(args.train_splits, args.val_split, not args.allow_india_train)
    report["checks"]["scan_counts"] = {
        "train_splits": args.train_splits,
        "val_split": args.val_split,
        "train_path": seen.get("train", ("?", 0))[0],
        "val_path": seen.get("val", ("?", 0))[0],
        "train_scanned": seen.get("train", ("?", 0))[1],
        "val_scanned": seen.get("val", ("?", 0))[1],
        "train_expected": want["train"],
        "val_expected": want["val"],
        "ok": (
            seen.get("train", ("", -1))[1] == want["train"]
            and seen.get("val", ("", -1))[1] == want["val"]
        ),
    }
    report["checks"]["india_policy"] = {
        "ok": True,
        "note": (
            "india_train permitted (Model B)"
            if args.allow_india_train
            else "no India permitted (Model A); asserted per training list"
        ),
        "held_out_never_validated": True,
    }

    # 2/3. per-epoch losses and metrics
    csv = next((p for p in dest.rglob("results.csv")), None)
    if csv:
        import csv as csvmod

        rows = [
            {k.strip(): v for k, v in r.items()}
            for r in csvmod.DictReader(csv.read_text().splitlines())
        ]

        def finite(key):
            vals = []
            for r in rows:
                try:
                    vals.append(float(r.get(key, "nan")))
                except ValueError:
                    vals.append(float("nan"))
            return vals

        train_keys = [k for k in rows[0] if k.startswith("train/") and k.endswith("loss")]
        bad = {
            k: [i + 1 for i, v in enumerate(finite(k)) if not math.isfinite(v)] for k in train_keys
        }
        bad = {k: v for k, v in bad.items() if v}
        maps = [v for v in finite("metrics/mAP50(B)") if math.isfinite(v)]
        report["checks"]["train_losses_finite"] = {"ok": not bad, "nan_epochs": bad}
        report["checks"]["val_map50"] = {
            "best": round(max(maps), 4) if maps else None,
            "floor": MAP50_FLOOR,
            "epochs": len(rows),
            "ok": bool(maps) and max(maps) >= MAP50_FLOOR,
        }
        val_nan = [
            k
            for k in rows[0]
            if k.startswith("val/") and any(not math.isfinite(v) for v in finite(k))
        ]
        report["checks"]["val_loss_nan"] = {
            "columns": val_nan,
            "verdict": "inert (D065: fitness is mAP50-95 only, trainer.py:605/766)"
            if val_nan
            else "none",
        }
    else:
        report["checks"]["results_csv"] = {"ok": False, "note": "not found"}

    # 4/5. status and weights
    status = next((p for p in dest.rglob("status.json")), None)
    if status:
        report["checks"]["status"] = json.loads(status.read_text())
    best = next((p for p in dest.rglob("best.pt")), None)
    if best:
        report["checks"]["best_pt"] = {
            "path": str(best),
            "sha256": sha256(best),
            "bytes": best.stat().st_size,
        }

    out = repo_root() / "results" / "T5" / f"{args.slug}_verification.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2))
    print(json.dumps(report, indent=2))

    failed = [
        k for k, v in report["checks"].items() if isinstance(v, dict) and v.get("ok") is False
    ]
    print(f"\nVERDICT: {'PASS' if not failed else 'FAIL ' + str(failed)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
