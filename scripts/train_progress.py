"""Show YOLO training progress at a glance.

Usage: uv run python scripts/train_progress.py [RUN_DIR]

`RUN_DIR` defaults to the most recently updated run under
`runs/detect/models/yolo/`. `epochs`/`patience` are read from the run's own
`args.yaml` rather than hardcoded, so this works for any run (the india_v1
v8n baseline, the multicountry_v8s run, or any future one) without editing
this file.

Reads ultralytics' results.csv, so it works whether or not the run was started
from this shell, and it never touches the training process.
"""

import csv
import subprocess
import sys
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from certain_road.core.paths import repo_root  # noqa: E402

RUNS_ROOT = repo_root() / "runs/detect/models/yolo"
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


def newest_run_dir() -> Path | None:
    """The run directory with the most recently modified `results.csv`."""
    candidates = [d for d in RUNS_ROOT.glob("*") if (d / "results.csv").is_file()]
    if not candidates:
        return None
    return max(candidates, key=lambda d: (d / "results.csv").stat().st_mtime)


def resolve_run_dir() -> Path | None:
    if len(sys.argv) > 1:
        return Path(sys.argv[1]).resolve()
    return newest_run_dir()


def load_run_args(run_dir: Path) -> dict:
    args_path = run_dir / "args.yaml"
    if not args_path.exists():
        raise SystemExit(f"no args.yaml in {run_dir}; is this an ultralytics run directory?")
    return yaml.safe_load(args_path.read_text())


def main() -> None:
    pid = training_pid()
    print(f"process   : {'RUNNING pid ' + pid if pid else 'not running'}")

    run_dir = resolve_run_dir()
    if run_dir is None:
        print(f"results   : no run with a results.csv found under {RUNS_ROOT}")
        return

    results = run_dir / "results.csv"
    weights = run_dir / "weights"
    if not results.exists():
        print(f"results   : none yet at {results}")
        return

    run_args = load_run_args(run_dir)
    total_epochs = run_args["epochs"]
    patience = run_args["patience"]

    print(f"run       : {run_dir}")

    rows = list(csv.DictReader(results.open()))
    if not rows:
        print("results   : file exists but no epochs recorded yet")
        return

    done = int(rows[-1]["epoch"])
    elapsed = float(rows[-1]["time"])

    window = min(RATE_WINDOW, len(rows) - 1)
    rate = (elapsed - float(rows[-1 - window]["time"])) / window if window > 0 else elapsed / done
    remaining = (total_epochs - done) * rate

    print(f"epoch     : {done}/{total_epochs}  ({100 * done // total_epochs}%)")
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
    print(f"early stop    : {stale}/{patience} epochs without improvement")

    print()
    print("last 5 epochs")
    cols = ["metrics/precision(B)", "metrics/recall(B)", "metrics/mAP50(B)", key]
    print("  ep  " + "  ".join(f"{c.split('/')[-1]:>12}" for c in cols))
    for r in rows[-5:]:
        print(f"  {r['epoch']:>2}  " + "  ".join(f"{float(r[c]):>12.4f}" for c in cols))

    if weights.exists():
        print()
        for w in sorted(weights.glob("*.pt")):
            print(f"checkpoint: {w.name}  {w.stat().st_size / 1e6:.0f} MB")


if __name__ == "__main__":
    main()
