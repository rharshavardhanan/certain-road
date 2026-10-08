"""Score a Gazebo closed-loop run against the road's ground truth and a baseline run.

    python -m sim.gazebo.closed_loop --world runs/gazebo/poor_seed0 \
        --run runs/gazebo/poor_seed0/cl_run --baseline runs/gazebo/poor_seed0/cl_base

A run folder is what runs/gazebo/closed_loop.sh leaves: the recorder's odom.jsonl,
joints.jsonl, frames.jsonl and summary.json (sim/gazebo/capture.py --record-only), and
run_dir.txt naming the runs/ros/<stamp>/ folder with the planner's decisions.jsonl,
can_monitor_node's can_frames.jsonl and the stand-in driver's lane_keeper.json.

- **Crossings.** A wheel crosses a pothole when its tyre (the contact point under the wheel
  centre, from the true pose, widened by half the tyre's width) enters the pothole's ellipse:
  the ground truth's footprint, the outline the surface baker paints and relief.py sinks.
- **In-lane potholes** are those whose ellipse reaches into the driving lane.
- **Avoided** is a pothole a wheel crossed in the baseline (the stand-in driver alone, no
  planner) and no wheel crossed in the closed loop. **New** is the reverse: a manoeuvre
  that put a wheel into a pothole the baseline missed.
- **Planner states per pothole**: every decision made while the pothole's near edge was
  between the camera and the corridor's look-ahead.
- **False onsets**: a reaction (NORMAL -> anything) or manoeuvre (-> AVOID or STOP) that
  began with no pothole in the corridor's ground strip ahead (|y| <= W, out to the
  look-ahead, from configs/driving/corridor_car.yaml's derivation). Whether a crack was
  there instead is said, since Model P is known to fire on alligator cracks (D089).
- **Frames**: camera frames in the drive (the recorder counts camera_info) against the
  frames the planner judged; the difference is what perception dropped.

It measures one pair of runs; nothing here is tuned.
"""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path

import numpy as np
import yaml

from certain_road.core.paths import repo_root
from sim.gazebo.derive import car_corridor
from sim.gazebo.evaluate import quat_mat, ride_events, wheel_offsets
from sim.gazebo.export import load_gz
from sim.mujoco.road import Road, load_config

MANOEUVRES = ("avoid_left", "avoid_right", "stop")


def inside_ellipse(px, py, inst, grow: float = 0.0) -> np.ndarray:
    """Whether points (px, py) lie in the instance's ellipse, its semi-axes grown by `grow`."""
    c, s = math.cos(inst.angle_rad), math.sin(inst.angle_rad)
    dx, dy = np.asarray(px) - inst.x_m, np.asarray(py) - inst.y_m
    u = (dx * c + dy * s) / (inst.length_m / 2 + grow)
    v = (-dx * s + dy * c) / (inst.width_m / 2 + grow)
    return u * u + v * v <= 1.0


def in_lane(inst, lane: tuple[float, float], n: int) -> bool:
    """Whether any of the ellipse's outline points (or its centre) lies inside the lane."""
    t = np.linspace(0, 2 * math.pi, n, endpoint=False)
    c, s = math.cos(inst.angle_rad), math.sin(inst.angle_rad)
    ex, ey = inst.length_m / 2 * np.cos(t), inst.width_m / 2 * np.sin(t)
    ys = np.r_[inst.y_m + ex * s + ey * c, inst.y_m]
    return bool(((ys > lane[0]) & (ys < lane[1])).any())


def wheel_tracks(odom: np.ndarray, gz: dict) -> dict[str, np.ndarray]:
    """Each wheel's contact point in the world, per odometry row: {wheel: (n, 2)}."""
    rot = [quat_mat(q) for q in odom[:, 4:8]]
    return {
        name: np.array([p + r @ off for p, r in zip(odom[:, 1:4], rot, strict=True)])[:, :2]
        for name, off in wheel_offsets(gz).items()
    }


def crossings(road: Road, tracks: dict[str, np.ndarray], grow: float) -> dict[int, list[str]]:
    """{pothole id: [wheels whose tyre entered it]}, for every pothole some wheel entered."""
    out: dict[int, list[str]] = {}
    for inst in road.instances:
        if inst.cls != "pothole":
            continue
        hit = [
            w for w, xy in tracks.items() if inside_ellipse(xy[:, 0], xy[:, 1], inst, grow).any()
        ]
        if hit:
            out[inst.id] = hit
    return out


def _pose_at(odom: np.ndarray, t: float) -> tuple[np.ndarray, float]:
    k = int(np.clip(np.searchsorted(odom[:, 0], t), 0, len(odom) - 1))
    q = odom[k, 4:8]
    yaw = math.atan2(2 * (q[0] * q[3] + q[1] * q[2]), 1 - 2 * (q[2] ** 2 + q[3] ** 2))
    return odom[k, 1:3], yaw


def ahead(road: Road, odom: np.ndarray, t: float, cam_x: float, half: float, reach: float):
    """Instances whose ellipse enters the corridor strip ahead of the camera at time t:
    {class: [ids]}. The strip is |y| <= half, from the camera out to `reach`, car frame."""
    pos, yaw = _pose_at(odom, t)
    c, s = math.cos(yaw), math.sin(yaw)
    origin = pos + cam_x * np.array([c, s])
    n = 32
    out: dict[str, list[int]] = {}
    for inst in road.instances:
        if abs(inst.x_m - origin[0]) > reach + inst.length_m:
            continue
        tt = np.linspace(0, 2 * math.pi, n, endpoint=False)
        ca, sa = math.cos(inst.angle_rad), math.sin(inst.angle_rad)
        ex, ey = inst.length_m / 2 * np.cos(tt), inst.width_m / 2 * np.sin(tt)
        px = np.r_[inst.x_m + ex * ca - ey * sa, inst.x_m] - origin[0]
        py = np.r_[inst.y_m + ex * sa + ey * ca, inst.y_m] - origin[1]
        fwd, left = px * c + py * s, -px * s + py * c
        if ((fwd > 0) & (fwd <= reach) & (np.abs(left) <= half)).any():
            out.setdefault(inst.cls, []).append(inst.id)
    return out


def episodes(decisions: list[dict], odom: np.ndarray, states: tuple[str, ...]) -> dict:
    """Runs of consecutive decisions in `states`: how long each lasted, and how far the car
    moved sideways from the run's start to its end (true pose)."""
    runs, start = [], None
    for k, d in enumerate([*decisions, {"state": "", "stamp": None}]):
        if d["state"] in states and start is None:
            start = k
        elif d["state"] not in states and start is not None:
            t0, t1 = _t(decisions[start]["stamp"]), _t(decisions[k - 1]["stamp"])
            y0, y1 = np.interp([t0, t1], odom[:, 0], odom[:, 2])
            runs.append({"frames": k - start, "s": t1 - t0, "lateral_m": abs(y1 - y0)})
            start = None
    if not runs:
        return {"count": 0}
    f = [r["frames"] for r in runs]
    lat = [r["lateral_m"] for r in runs]
    return {
        "count": len(runs),
        "frames_median": float(np.median(f)),
        "frames_max": int(max(f)),
        "single_frame": sum(1 for x in f if x == 1),
        "lateral_m_median": round(float(np.median(lat)), 3),
        "lateral_m_max": round(float(max(lat)), 3),
    }


def deepest(road: Road, tracks: dict[str, np.ndarray], look: dict, ids: list[int]) -> dict:
    """{pothole id: deepest relief (m) under any wheel's contact centre}: how far a wheel
    actually dropped, beside whether its tyre touched the footprint at all."""
    from sim.mujoco.relief import depth_at

    by_id = {i.id: i for i in road.instances}
    out = {}
    for pid in ids:
        p = by_id[pid]
        best = 0.0
        for xy in tracks.values():  # only inside this pothole's own ellipse, not a neighbour's
            mine = inside_ellipse(xy[:, 0], xy[:, 1], p)
            if mine.any():
                best = max(best, float(depth_at(road, look, xy[mine, 0], xy[mine, 1]).max()))
        out[pid] = round(best, 4)
    return out


def payload_agreement(decisions: list[dict], vehicle_yaml: Path) -> dict:
    """Each decision's CAN payload decoded through the vehicle profile, against the Twist
    RosTransport sent for the same Command: they differ only by the bytes' quantisation."""
    from certain_road.canbus.protocol import Command
    from certain_road.sim.model import command_velocity, load_robot

    robot = load_robot(vehicle_yaml)
    dv, dw = [], []
    for d in decisions:
        v, w = command_velocity(Command.from_bytes(bytes.fromhex(d["payload"])), robot)
        dv.append(abs(v - d["twist"][0]))
        dw.append(abs(w - d["twist"][1]))
    return {
        "decisions": len(decisions),
        "max_abs_diff_mps": round(max(dv), 5) if dv else None,
        "max_abs_diff_radps": round(max(dw), 5) if dw else None,
    }


def load_run(folder: Path) -> dict:
    run_dir = repo_root() / (folder / "run_dir.txt").read_text().strip()
    odom = np.array([json.loads(line)[:9] for line in (folder / "odom.jsonl").open()])
    odom = odom[np.argsort(odom[:, 0], kind="stable")]
    out = {
        "folder": folder,
        "run_dir": run_dir,
        "odom": odom,
        "joints": [json.loads(line) for line in (folder / "joints.jsonl").open()],
        "frames": [json.loads(line) for line in (folder / "frames.jsonl").open()],
        "summary": json.loads((folder / "summary.json").read_text()),
        "decisions": [],
        "can": [],
        "keeper": None,
    }
    for name, key in (("decisions.jsonl", "decisions"), ("can_frames.jsonl", "can")):
        path = run_dir / name
        if path.exists():
            out[key] = [json.loads(line) for line in path.open()]
    if (run_dir / "lane_keeper.json").exists():
        out["keeper"] = json.loads((run_dir / "lane_keeper.json").read_text())
    return out


def _t(stamp) -> float:
    return stamp[0] + stamp[1] * 1e-9


def score(world: Path, run: dict, base: dict) -> dict:
    gz = load_gz()
    look = load_config(gz["look"])
    road = Road.from_json((world / "ground_truth.json").read_text())
    meta = json.loads((world / "world.json").read_text())
    car = yaml.safe_load((repo_root() / "ros/certain_road_gz/config/car.yaml").read_text())
    project_cfg = yaml.safe_load((repo_root() / "configs/project.yaml").read_text())
    decision = yaml.safe_load((repo_root() / "configs/driving/decision.yaml").read_text())
    robot_corridor = yaml.safe_load((repo_root() / "configs/driving/corridor.yaml").read_text())
    nums = car_corridor(gz, project_cfg, decision, robot_corridor)["_numbers"]
    half, reach = nums["half_width_m"], nums["far_m"]
    cam_x = car["camera_xyz"][0]
    grow = gz["vehicle"]["wheel"]["width_m"] / 2
    centre = meta["road"]["drive_lane_y"]
    lane = (centre - road.lane_width_m / 2, centre + road.lane_width_m / 2)
    by_id = {i.id: i for i in road.instances}
    n = look["survey"]["gt_outline_points"]
    end_x = run["odom"][-1, 1]

    tracks = {k: wheel_tracks(r["odom"], gz) for k, r in (("run", run), ("base", base))}
    crossed = {k: crossings(road, v, grow) for k, v in tracks.items()}
    crossed_centre = {k: crossings(road, v, 0.0) for k, v in tracks.items()}
    reached = min(end_x, base["odom"][-1, 1]) + cam_x
    lane_pots = [
        i for i in road.instances if i.cls == "pothole" and in_lane(i, lane, n) and i.x_m < reached
    ]

    frames = [d for d in run["decisions"] if d["trigger"] == "frame"]
    t_dec = np.array([_t(d["stamp"]) for d in frames])
    x_dec = np.interp(t_dec, run["odom"][:, 0], run["odom"][:, 1]) + cam_x
    depth = {k: deepest(road, v, look, [p.id for p in lane_pots]) for k, v in tracks.items()}
    per_pothole = []
    for p in lane_pots:
        near_edge = p.bbox[0]
        win = (near_edge - x_dec > 0) & (near_edge - x_dec <= reach)
        states = [frames[k]["state"] for k in np.flatnonzero(win)]
        first = next(
            (
                round(float(near_edge - x_dec[k]), 2)
                for k in np.flatnonzero(win)
                if frames[k]["state"] != "normal"
            ),
            None,
        )
        per_pothole.append(
            {
                "id": p.id,
                "x_m": p.x_m,
                "y_m": p.y_m,
                "size_m": [p.length_m, p.width_m],
                "decisions_in_approach": len(states),
                "states": sorted(set(states)),
                "first_reaction_at_m": first,
                "crossed_baseline": crossed["base"].get(p.id, []),
                "crossed_closed_loop": crossed["run"].get(p.id, []),
                "deepest_wheel_drop_m": {
                    "baseline": depth["base"][p.id],
                    "closed_loop": depth["run"][p.id],
                },
            }
        )
    in_lane_ids = {p.id for p in lane_pots}
    base_hit = {i for i in crossed["base"] if i in in_lane_ids}
    run_hit = {i for i in crossed["run"] if i in in_lane_ids}
    any_run_hit = {i for i in crossed["run"] if by_id[i].x_m < reached}

    onsets = {"reaction": [], "manoeuvre": []}
    prev = "normal"
    for d in run["decisions"]:
        state = d["state"]
        if prev == "normal" and state != "normal":
            onsets["reaction"].append(d)
        if state in MANOEUVRES and prev not in MANOEUVRES:
            onsets["manoeuvre"].append(d)
        prev = state
    false = {}
    for kind, rows in onsets.items():
        listed = []
        for d in rows:
            t = _t(d["stamp"]) if d["stamp"] else None
            if t is None:  # a staleness failsafe has no frame: judged at the previous one
                listed.append({"state": d["state"], "trigger": d["trigger"], "pothole_ahead": None})
                continue
            what = ahead(road, run["odom"], t, cam_x, half, reach)
            x = float(np.interp(t, run["odom"][:, 0], run["odom"][:, 1])) + cam_x
            listed.append(
                {
                    "t_s": round(t, 3),
                    "camera_x_m": round(x, 2),
                    "state": d["state"],
                    "pothole_ahead": what.get("pothole", []),
                    "cracks_ahead": what.get("alligator_crack", []) + what.get("linear_crack", []),
                }
            )
        false[kind] = {
            "onsets": len(listed),
            "without_pothole_ahead": sum(1 for r in listed if r["pothole_ahead"] == []),
            "of_which_crack_ahead": sum(
                1 for r in listed if r["pothole_ahead"] == [] and r.get("cracks_ahead")
            ),
            "list": listed,
        }

    rec = run["frames"]
    frame_stamps = {round(f["stamp"], 4) for f in rec}
    judged = {round(_t(d["stamp"]), 4) for d in frames}
    states = [d["state"] for d in run["decisions"]]
    can_sent = sum(1 for d in run["decisions"] if d.get("can"))
    out = {
        "world": world.name,
        "corridor": {"half_width_m": round(half, 3), "look_ahead_m": reach, "tyre_grow_m": grow},
        "in_lane_potholes": len(lane_pots),
        "crossed": {
            "baseline": sorted(base_hit),
            "closed_loop": sorted(run_hit),
            "avoided": sorted(base_hit - run_hit),
            "new": sorted(run_hit - base_hit),
            "closed_loop_any_lane": sorted(any_run_hit),
            "centre_only": {
                "baseline": sorted(i for i in crossed_centre["base"] if i in in_lane_ids),
                "closed_loop": sorted(i for i in crossed_centre["run"] if i in in_lane_ids),
            },
        },
        "per_pothole": per_pothole,
        "states": {s: states.count(s) for s in sorted(set(states))},
        "avoid_episodes": episodes(run["decisions"], run["odom"], ("avoid_left", "avoid_right")),
        "reaction_episodes": episodes(run["decisions"], run["odom"], MANOEUVRES + ("warning",)),
        "wheel_drops_deeper_than_ride_threshold": {
            k: sum(1 for v in depth[kk].values() if v >= gz["evaluate"]["ride"]["wheel_drop_m"])
            for k, kk in (("baseline", "base"), ("closed_loop", "run"))
        },
        "stale_decisions": sum(1 for d in run["decisions"] if d["trigger"] == "stale"),
        "false_onsets": false,
        "can": {
            "decisions": len(run["decisions"]),
            "sent": can_sent,
            "read_back": len(run["can"]),
            "decoded": sum(1 for c in run["can"] if c["ok"]),
            # without a bus: the payloads as logged, decoded through the same car profile
            "payload_vs_cmd_vel": payload_agreement(
                run["decisions"], repo_root() / "configs/sim/car.yaml"
            ),
        },
        "frames": {
            "camera": len(frame_stamps),
            "judged": len(judged & frame_stamps),
            "dropped": len(frame_stamps - judged),
        },
        "lateral_m": {
            k: round(float(np.abs(r["odom"][:, 2] - meta["spawn"]["y"]).max()), 3)
            for k, r in (("closed_loop", run), ("baseline", base))
        },
        "drive": {
            k: {
                f: r["summary"].get(f)
                for f in (
                    "real_time_factor",
                    "drive_sim_s",
                    "drive_wall_s",
                    "camera_hz_sim",
                    "camera_hz_wall",
                    "load_s",
                    "gz_rss_mb_max",
                    "mem_available_mb",
                    "timed_out",
                )
            }  # fmt: skip
            for k, r in (("closed_loop", run), ("baseline", base))
        },
        "stand_in_driver": {"closed_loop": run["keeper"], "baseline": base["keeper"]},
        "ride": {
            k: ride_events(r["odom"], r["joints"], road, look, gz)
            for k, r in (("closed_loop", run), ("baseline", base))
        },
    }
    return out


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--world", type=Path, required=True)
    ap.add_argument("--run", type=Path, required=True, help="the closed-loop run folder")
    ap.add_argument("--baseline", type=Path, required=True, help="the lane-keep-only run folder")
    ap.add_argument("--out", type=Path, help="default: <run>/closed_loop_score.json")
    args = ap.parse_args()
    result = score(args.world.resolve(), load_run(args.run), load_run(args.baseline))
    out = args.out or args.run / "closed_loop_score.json"
    out.write_text(json.dumps(result, indent=1))
    brief = {k: v for k, v in result.items() if k not in ("per_pothole", "ride", "false_onsets")}
    brief["false_onsets"] = {
        k: {kk: vv for kk, vv in v.items() if kk != "list"}
        for k, v in result["false_onsets"].items()
    }
    print(json.dumps(brief, indent=1))
    print(f"-> {out}")


if __name__ == "__main__":
    main()
