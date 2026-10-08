"""Survey three simulated roads one after another, and build one report over all of them.

    .venv/bin/python scripts/survey_environments.py              # reuse complete runs, then build
    .venv/bin/python scripts/survey_environments.py --force      # drive and re-render every road
    .venv/bin/python scripts/survey_environments.py --report-only

Roads, lock and output come from configs/report/survey_environments.yaml. For each road, in
order:

1. **Drive** with the real models: `python -m sim.mujoco.demo --headless --record --still`,
   recording the live screen to runs/mujoco/<preset>_seed<seed>_v2.mp4. Skipped when the run
   directory already holds a complete drive (every log present, the whole road driven).
2. **Gallery**: `python -m sim.mujoco.gallery` re-renders each confirmed track's frame from
   the logs and places it on the road. Skipped when gallery.json exists.
3. After every road: the **report**, runs/survey_environments/report.html (one offline file,
   D020) and report.json, from certain_road.dashboard.survey_report.

Steps 1 and 2 load YOLO or build a MuJoCo scene, so each runs under `flock` on the shared
lock: the Jetson's GPU is shared, and one heavy job at a time keeps it inside 7.3 GB. The
report step is light and takes no lock. This script only orchestrates; every number comes
from the stages it calls.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from datetime import UTC, datetime
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT))

from certain_road.dashboard.survey_report import (  # noqa: E402
    Pricing,
    RoadRun,
    build_report,
    downscale_jpeg,
    write,
)
from certain_road.survey.rsl import load_config as load_rsl  # noqa: E402

CONFIG = ROOT / "configs/report/survey_environments.yaml"
RUN_FILES = (
    "ground_truth.json",
    "detections.jsonl",
    "survey.json",
    "drive_summary.json",
    "end.json",
    "end_screen.png",
)


def sim_config(look: str) -> dict:
    from sim.mujoco.road import load_config

    return load_config(look)


def run_dir(road: dict, cfg: dict, sim: dict) -> Path:
    tag = "" if cfg["look"] == "v1" else f"_{cfg['look']}"
    return ROOT / sim["out_dir"] / f"{road['preset']}_seed{road['seed']}{tag}"


def drive_complete(d: Path, sim: dict) -> tuple[bool, str]:
    """Every log present and the whole road driven, not a run stopped early."""
    from sim.mujoco.drive import frame_positions

    missing = [f for f in RUN_FILES if not (d / f).exists()]
    if missing:
        return False, f"missing {', '.join(missing)}"
    length = json.loads((d / "ground_truth.json").read_text())["length_m"]
    expected = len(frame_positions(length, sim)[0])
    frames = json.loads((d / "drive_summary.json").read_text())["frames"]
    if frames != expected:
        return False, f"{frames} of {expected} frames driven"
    return True, f"complete: {frames} frames"


def heavy(cmd: list[str], cfg: dict, use_lock: bool, log: Path) -> float:
    """Run a heavy step under the shared lock; return its wall time, lock wait included."""
    full = (["flock", cfg["heavy_lock"]] if use_lock else []) + cmd
    print("$", " ".join(full), flush=True)
    t0 = time.perf_counter()
    with log.open("a") as f:
        subprocess.run(full, cwd=ROOT, check=True, stdout=f, stderr=subprocess.STDOUT)
    return time.perf_counter() - t0


def media(road: dict, d: Path, key: str, suffix: str) -> Path | None:
    own = d.parent / f"{d.name}{suffix}"
    if own.exists():
        return own
    fallback = road.get(f"{key}_fallback")
    return ROOT / fallback if fallback and (ROOT / fallback).exists() else None


def load_road(road: dict, d: Path, cfg: dict, sim: dict) -> RoadRun:
    from sim.mujoco.scene import design_camera

    e = cfg["embed"]
    gt = json.loads((d / "ground_truth.json").read_text())
    survey = json.loads((d / "survey.json").read_text())
    end = json.loads((d / "end.json").read_text())
    summary = json.loads((d / "drive_summary.json").read_text())
    gallery_path = d / "gallery.json"
    gallery = json.loads(gallery_path.read_text()) if gallery_path.exists() else None
    images = {}
    for t in (gallery or {}).get("tracks", []):
        for k in ("crop", "frame"):
            if t.get(k) and (d / t[k]).exists():
                images[t[k]] = (d / t[k]).read_bytes()
    stills = {}
    live = media(road, d, "still", "_last.png")
    if live is not None:
        stills["live"] = downscale_jpeg(live.read_bytes(), e["still_width_px"], e["jpeg_quality"])
    stills["end"] = downscale_jpeg(
        (d / "end_screen.png").read_bytes(), e["still_width_px"], e["jpeg_quality"]
    )
    recording = media(road, d, "recording", ".mp4")
    speed = design_camera()["speed_mps"]
    wall = summary.get("wall_s")
    return RoadRun(
        label=f"{road['preset'].capitalize()} road, seed {road['seed']}",
        preset=road["preset"],
        seed=road["seed"],
        look=cfg["look"],
        length_m=gt["length_m"],
        run_dir=str(d.relative_to(ROOT)),
        segments=survey["segments"],
        detection=end["detection"],
        drift_alarm_m=survey["drift"]["alarm_m"],
        gallery=gallery,
        images=images,
        stills=stills,
        recording=None if recording is None else str(recording.relative_to(ROOT)),
        timing={
            "frames": summary["frames"],
            "drive_wall_s": wall,
            "realtime_x": (summary["metres"] / speed) / wall if wall else None,
            "ms_p50": summary.get("ms_p50"),
            "gallery_s": (gallery or {}).get("timing_s"),
        },
    )


def stamp() -> dict:
    def git(*args: str) -> str:
        return subprocess.run(
            ["git", *args], capture_output=True, text=True, cwd=ROOT
        ).stdout.strip()

    commit = git("rev-parse", "--short", "HEAD") or "unknown"
    if git("status", "--porcelain"):
        commit += " with uncommitted changes"
    return {"utc": datetime.now(UTC).strftime("%Y-%m-%d %H:%M UTC"), "commit": commit}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--force", action="store_true", help="drive and re-render every road again")
    ap.add_argument("--report-only", action="store_true", help="build the report from what exists")
    ap.add_argument("--no-lock", action="store_true", help="do not wrap heavy steps in flock")
    ap.add_argument("--out", type=Path, help="report directory (default: config out_dir)")
    args = ap.parse_args()
    cfg = yaml.safe_load(CONFIG.read_text())
    sim = sim_config(cfg["look"])
    out = args.out or ROOT / cfg["out_dir"]
    out.mkdir(parents=True, exist_ok=True)
    log = out / "runner.log"
    steps = []
    py = str(ROOT / ".venv/bin/python")
    for road in cfg["roads"]:
        d = run_dir(road, cfg, sim)
        name = f"{road['preset']} seed {road['seed']}"
        ok, why = drive_complete(d, sim)
        if not args.report_only and (args.force or not ok):
            rec = d.parent / f"{d.name}.mp4"
            still = d.parent / f"{d.name}_last.png"
            cmd = [py, "-m", "sim.mujoco.demo", "--preset", road["preset"]]
            cmd += ["--seed", str(road["seed"]), "--look", cfg["look"], "--headless"]
            cmd += ["--record", str(rec), "--still", str(still)]
            s = heavy(cmd, cfg, not args.no_lock, log)
            steps.append({"road": name, "step": "drive", "wall_s": round(s, 1)})
            ok, why = drive_complete(d, sim)
        else:
            steps.append({"road": name, "step": "drive", "reused": why})
        if not ok:
            print(f"{name}: no complete drive ({why}); left out of the report", file=sys.stderr)
            continue
        if not args.report_only and (args.force or not (d / "gallery.json").exists()):
            cmd = [py, "-m", "sim.mujoco.gallery", "--preset", road["preset"]]
            cmd += ["--seed", str(road["seed"]), "--look", cfg["look"]]
            s = heavy(cmd, cfg, not args.no_lock, log)
            steps.append({"road": name, "step": "gallery", "wall_s": round(s, 1)})
    roads = []
    for road in cfg["roads"]:
        d = run_dir(road, cfg, sim)
        if drive_complete(d, sim)[0]:
            roads.append(load_road(road, d, cfg, sim))
    project = yaml.safe_load((ROOT / "configs/project.yaml").read_text())["allocation"]
    pricing = Pricing(
        mobilisation_cost=float(project["mobilisation_cost"]),
        cost_per_m2=float(project["cost_per_m2"]),
        budget_frac=float(sim["end"]["budget_frac"]),
        worst_share=project["worst_k"] / project["n_segments"],
    )
    rsl_cfg = load_rsl(ROOT / cfg["rsl_config"])
    page, data = build_report(roads, rsl_cfg, pricing, cfg, stamp())
    data["runner_steps"] = steps
    html_path, json_path = write(page, data, out)
    print(json.dumps(steps, indent=1))
    print(f"wrote {html_path} ({html_path.stat().st_size / 1e6:.1f} MB)")
    print(f"wrote {json_path}")
    plan = data["plan"]
    for k, p in plan["plans"].items():
        print(
            f"{k}: {len(p['chosen'])} segments, true benefit {p.get('true_benefit', 0):.1f}, "
            f"worst {p.get('worst_covered')} of {len(plan['worst'])}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
