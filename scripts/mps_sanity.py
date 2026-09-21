"""T4 — can this Mac train, and does MPS agree with CPU?

Trains one epoch of yolov8s at `fraction=0.02` on each backend with an identical
seed and compares the training losses. MPS has historically had op-level gaps
that produce *plausible* but wrong numbers, so the comparison is the point: a
loss that is merely non-zero proves nothing on its own.

Validation runs on MPS only. The pass criterion is about training losses, and a
full CPU pass over 6,142 val images would cost well over an hour to produce a
number nothing checks. The full val is timed once on MPS because the schedule
projection needs it — D060 uses these figures to decide whether the Mac is a
viable fallback for Model B.
"""

import json
import sys
import time
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from certain_road.core.paths import repo_root  # noqa: E402

FRACTION = 0.02
TOLERANCE = 0.25
LOSSES = ["train/box_loss", "train/cls_loss", "train/dfl_loss"]


def run(device: str, *, do_val: bool) -> dict:
    from ultralytics import YOLO

    out = repo_root() / "runs" / "t4" / f"sanity_{device}"
    print(f"\n===== {device} =====", flush=True)
    t0 = time.time()
    YOLO("yolov8s.pt").train(
        data=str(repo_root() / "configs" / "data" / "model_a.yaml"),
        epochs=1, fraction=FRACTION, batch=16, imgsz=640, seed=0, deterministic=True,
        device=device, workers=4, val=do_val, plots=False, save=False,
        project=str(repo_root() / "runs" / "t4"), name=f"sanity_{device}", exist_ok=True,
    )
    wall = time.time() - t0
    df = pd.read_csv(out / "results.csv")
    df.columns = df.columns.str.strip()
    return {"device": device, "wall_s": round(wall, 1), "validated": do_val,
            "losses": {k: float(df[k].iloc[-1]) for k in LOSSES if k in df.columns},
            "epoch_time_s": float(df["time"].iloc[-1]) if "time" in df.columns else None}


def time_full_val() -> float:
    from ultralytics import YOLO

    print("\n===== timing full non-India val on MPS =====", flush=True)
    t0 = time.time()
    YOLO("yolov8s.pt").val(
        data=str(repo_root() / "configs" / "data" / "model_a.yaml"),
        imgsz=640, batch=16, device="mps", verbose=False, plots=False,
        project=str(repo_root() / "runs" / "t4"), name="val_timing", exist_ok=True,
    )
    return time.time() - t0


def main() -> int:
    results = [run("mps", do_val=False), run("cpu", do_val=False)]
    val_s = time_full_val()

    mps, cpu = results[0]["losses"], results[1]["losses"]
    checks, worst = {}, 0.0
    for key in LOSSES:
        a, b = mps.get(key), cpu.get(key)
        if a is None or b is None:
            checks[key] = {"ok": False, "reason": "missing"}
            continue
        rel = abs(a - b) / max(abs(a), abs(b)) if max(abs(a), abs(b)) else 0.0
        worst = max(worst, rel)
        checks[key] = {"mps": round(a, 5), "cpu": round(b, 5),
                       "rel_diff": round(rel, 5),
                       "ok": a > 0 and b > 0 and rel < TOLERANCE}

    passed = all(c.get("ok") for c in checks.values())

    # fraction 0.02 -> full epoch: scale train time, then add one full val.
    mps_train_full = results[0]["wall_s"] / FRACTION
    payload = {
        "fraction": FRACTION, "tolerance": TOLERANCE, "pass": passed,
        "worst_rel_diff": round(worst, 5), "checks": checks, "runs": results,
        "full_val_s": round(val_s, 1),
        "projected_mps_epoch_s": round(mps_train_full + val_s, 1),
        "projected_model_a_40ep_h": round((mps_train_full + val_s) * 40 / 3600, 2),
    }
    out = repo_root() / "results"
    out.mkdir(parents=True, exist_ok=True)
    (out / "mps_sanity.json").write_text(json.dumps(payload, indent=2))
    print("\n" + json.dumps(payload, indent=2))
    print("\nT4:", "PASS" if passed else "FAIL")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
