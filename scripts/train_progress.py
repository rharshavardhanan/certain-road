"""Show YOLO training progress at a glance.

Usage: uv run python scripts/train_progress.py

Reads ultralytics' results.csv, so it works whether or not the run was started
from this shell, and it never touches the training process.
"""

import csv
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from certain_road.core.paths import repo_root  # noqa: E402

RESULTS = repo_root() / "runs/detect/models/yolo/india_v1/results.csv"
WEIGHTS = repo_root() / "runs/detect/models/yolo/india_v1/weights"
TOTAL_EPOCHS = 100
PATIENCE = 20
RATE_WINDOW = 10  # epochs to average for the steady-state rate


def training_pid() -> str | None:
    """PID of a live ultralytics training process, if any."""
    out = subprocess.run(
        ["pgrep", "-f", "ultralytics|certain-road detect train"],
        capture_output=True,
        text=True,
        check=False,
    )
    pids = [p for p in out.stdout.split() if p]
    return pids[-1] if pids else None


def main() -> None:
    pid = training_pid()
    print(f"process   : {'RUNNING pid ' + pid if pid else 'not running'}")

    if not RESULTS.exists():
        print(f"results   : none yet at {RESULTS}")
        return

    rows = list(csv.DictReader(RESULTS.open()))
    if not rows:
        print("results   : file exists but no epochs recorded yet")
        return

    done = int(rows[-1]["epoch"])
    elapsed = float(rows[-1]["time"])

    window = min(RATE_WINDOW, len(rows) - 1)
    rate = (elapsed - float(rows[-1 - window]["time"])) / window if window > 0 else elapsed / done
    remaining = (TOTAL_EPOCHS - done) * rate

    print(f"epoch     : {done}/{TOTAL_EPOCHS}  ({100 * done // TOTAL_EPOCHS}%)")
    print(f"rate      : {rate / 60:.2f} min/epoch (last {window} epochs)")
    print(f"elapsed   : {elapsed / 60:.0f} min")
    print(f"remaining : {remaining / 60:.0f} min  (~{remaining / 3600:.1f} h)")

    key = "metrics/mAP50-95(B)"
    best = max(rows, key=lambda r: float(r[key]))
    best_ep = int(best["epoch"])
    stale = done - best_ep
    print()
    print(f"best mAP50-95 : {float(best[key]):.4f}  at epoch {best_ep}")
    print(f"latest mAP50  : {float(rows[-1]['metrics/mAP50(B)']):.4f}")
    print(f"early stop    : {stale}/{PATIENCE} epochs without improvement")

    print()
    print("last 5 epochs")
    cols = ["metrics/precision(B)", "metrics/recall(B)", "metrics/mAP50(B)", key]
    print("  ep  " + "  ".join(f"{c.split('/')[-1]:>12}" for c in cols))
    for r in rows[-5:]:
        print(f"  {r['epoch']:>2}  " + "  ".join(f"{float(r[c]):>12.4f}" for c in cols))

    if WEIGHTS.exists():
        print()
        for w in sorted(WEIGHTS.glob("*.pt")):
            print(f"checkpoint: {w.name}  {w.stat().st_size / 1e6:.0f} MB")


if __name__ == "__main__":
    main()
