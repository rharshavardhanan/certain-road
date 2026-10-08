"""Did the closed loop keep the wheels out of the potholes? (D097)

    python -m sim.gazebo.avoidance --world runs/gazebo/poor_seed0 --runs cl_plan cl_base

Compares closed-loop drives (planner on) with the lane-keep-only baseline over the same
stretch of the same road. A wheel **drove over** a pothole when its contact point, from the
car's true pose on /odom, passed over relief at least `evaluate.ride.wheel_drop_m` deep
(`sim.mujoco.relief.depth_at`, the depth the collision mesh has). Counted at any speed: the
planner slows down to avoid, so the ride evaluation's cruise-only filter would hide hits.

What it is not: a field result. The road, the car and the lane keeper are simulated, and the
lane keeper is a stand-in driver steering on the true pose.
"""

from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path

import numpy as np

from certain_road.core.paths import repo_root
from sim.gazebo.evaluate import quat_mat, wheel_offsets
from sim.gazebo.export import load_gz
from sim.mujoco.road import Road, load_config


def potholes_driven_over(odom: np.ndarray, road: Road, look: dict, gz: dict) -> dict:
    """{pothole id: [wheels that went over it]} for one drive."""
    from sim.mujoco.relief import depth_at

    drop = gz["evaluate"]["ride"]["wheel_drop_m"]
    pots = [i for i in road.instances if i.cls == "pothole"]
    rot = [quat_mat(q) for q in odom[:, 4:8]]
    hits: dict[int, set[str]] = {}
    for name, off in wheel_offsets(gz).items():
        pts = np.array([p + r @ off for p, r in zip(odom[:, 1:4], rot, strict=True)])
        deep = depth_at(road, look, pts[:, 0], pts[:, 1]) >= drop
        for x, y in pts[deep][:, :2]:
            nearest = min(pots, key=lambda i: (i.x_m - x) ** 2 + (i.y_m - y) ** 2)
            hits.setdefault(nearest.id, set()).add(name)
    return {k: sorted(v) for k, v in sorted(hits.items())}


def in_lane_potholes(road: Road, look: dict, x0: float, x1: float) -> list[int]:
    """Potholes whose centre lies in the driving lane between x0 and x1."""
    half = look["road"]["lane_width_m"] / 2
    return [
        i.id
        for i in road.instances
        if i.cls == "pothole" and x0 <= i.x_m <= x1 and abs(i.y_m - road.drive_lane_y) < half
    ]


def drive_report(world: Path, run: str, road: Road, look: dict, gz: dict) -> dict:
    d = world / run
    odom = np.array([json.loads(line)[:9] for line in (d / "odom.jsonl").open()])
    x0, x1 = float(odom[:, 1].min()), float(odom[:, 1].max())
    hits = potholes_driven_over(odom, road, look, gz)
    lane = in_lane_potholes(road, look, x0, x1)
    out = {
        "run": run,
        "x_m": [round(x0, 1), round(x1, 1)],
        "max_lateral_from_lane_centre_m": round(
            float(np.abs(odom[:, 2] - road.drive_lane_y).max()), 2
        ),
        "in_lane_potholes": len(lane),
        "potholes_driven_over": len(hits),
        "in_lane_potholes_driven_over": sum(k in lane for k in hits),
        "driven_over": hits,
    }
    run_dir = (d / "run_dir.txt").read_text().strip() if (d / "run_dir.txt").exists() else ""
    if run_dir:
        rd = repo_root() / run_dir
        if (rd / "decisions.jsonl").exists():
            dec = [json.loads(line) for line in (rd / "decisions.jsonl").open()]
            states = [r["state"] for r in dec]
            out["decisions"] = len(dec)
            out["states"] = dict(Counter(states))
            out["manoeuvre_onsets"] = sum(
                s.startswith("avoid") and (i == 0 or not states[i - 1].startswith("avoid"))
                for i, s in enumerate(states)
            )
        if (rd / "can_frames.jsonl").exists():
            can = [json.loads(line) for line in (rd / "can_frames.jsonl").open()]
            out["can_frames_decoded"] = len(can)
            out["can_frames_ok"] = sum(bool(r.get("ok")) for r in can)
    return out


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--world", type=Path, required=True)
    ap.add_argument("--runs", nargs="+", required=True, help="drive folders inside the world")
    args = ap.parse_args()
    gz = load_gz()
    look = load_config(gz["look"])
    road = Road.from_json((args.world / "ground_truth.json").read_text())
    report = [drive_report(args.world, r, road, look, gz) for r in args.runs]
    out = args.world / "avoidance.json"
    out.write_text(json.dumps(report, indent=1))
    print(json.dumps(report, indent=1))
    print(f"-> {out}")


if __name__ == "__main__":
    main()
