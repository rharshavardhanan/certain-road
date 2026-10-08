"""Score the evidence drive: did Model P and Model B find the ground truth in Gazebo's frames?

    python -m sim.gazebo.evaluate --world runs/gazebo/poor_seed0

Reads <world>/drive/ (sim/gazebo/capture.py) and <world>/ground_truth.json, runs both models
on every frame, and writes <world>/drive/eval.json and detections.jsonl, plus annotated PNGs
and an mp4 under runs/gazebo/evidence_<world>/.

- **Ground truth per frame.** Each instance's ellipse, the outline the baker paints, at road
  level, is projected through the camera's true pose in that frame: the odometry
  interpolated to the frame's stamp, times the camera's mounting (config/car.yaml), with
  the intrinsics Gazebo reports (camera_info). The pose carries the suspension's pitch and
  roll, which the MuJoCo demo's fixed camera does not have.
- **In view**, as the MuJoCo demo counts it (sim/mujoco/evaluate.py, D090): the projected
  box reaches below the row where the 12 m detect range meets the road.
- **Boxed**: a box of the instance's class from the model that owns it (D082: potholes from
  P, cracks from B) overlapping the projected box with IoU above `end.iou_min`, at the video
  lane's conf (0.25). Counted two ways: in any frame (plain `predict`), and by a confirmed
  track (ByteTrack and D075's 3 of 5, `eval_video.confirm_step`), the MuJoCo demo's recall.
- **Ride**: where a wheel's path crosses a pothole deep enough (relief.depth_at, the same
  geometry the world's collision mesh has), the body's heave, pitch and roll and that
  corner's suspension travel against the second before it.

Nothing here tunes anything. It measures one drive.
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path

import cv2
import numpy as np
import yaml

from certain_road.core.geometry import project
from certain_road.core.paths import repo_root
from sim.gazebo.export import load_gz
from sim.mujoco.evaluate import iou
from sim.mujoco.road import CLASSES, Road, load_config

PROJECT = yaml.safe_load((repo_root() / "configs/project.yaml").read_text())
VIDEO = yaml.safe_load((repo_root() / "configs/eval/video.yaml").read_text())
CAR = repo_root() / "ros/certain_road_gz/config/car.yaml"


def quat_mat(q) -> np.ndarray:
    """Rotation matrix of a w-x-y-z quaternion."""
    w, x, y, z = np.asarray(q, float) / np.linalg.norm(q)
    return np.array(
        [
            [1 - 2 * (y * y + z * z), 2 * (x * y - w * z), 2 * (x * z + w * y)],
            [2 * (x * y + w * z), 1 - 2 * (x * x + z * z), 2 * (y * z - w * x)],
            [2 * (x * z - w * y), 2 * (y * z + w * x), 1 - 2 * (x * x + y * y)],
        ]
    )


def rpy_mat(roll: float, pitch: float, yaw: float) -> np.ndarray:
    """SDF's fixed-axis roll, pitch, yaw: Rz(yaw) Ry(pitch) Rx(roll)."""
    cr, sr, cp, sp = math.cos(roll), math.sin(roll), math.cos(pitch), math.sin(pitch)
    cy, sy = math.cos(yaw), math.sin(yaw)
    rx = np.array([[1, 0, 0], [0, cr, -sr], [0, sr, cr]])
    ry = np.array([[cp, 0, sp], [0, 1, 0], [-sp, 0, cp]])
    rz = np.array([[cy, -sy, 0], [sy, cy, 0], [0, 0, 1]])
    return rz @ ry @ rx


def euler(r: np.ndarray) -> tuple[float, float, float]:
    """(roll, pitch, yaw) of a rotation matrix, the inverse of `rpy_mat`."""
    pitch = math.asin(max(-1.0, min(1.0, -r[2, 0])))
    return math.atan2(r[2, 1], r[2, 2]), pitch, math.atan2(r[1, 0], r[0, 0])


def interp_pose(odom: np.ndarray, t: float) -> tuple[np.ndarray, np.ndarray]:
    """Body position and w-x-y-z quaternion at time t, from rows [t, x, y, z, qw, qx, qy, qz]."""
    k = int(np.clip(np.searchsorted(odom[:, 0], t), 1, len(odom) - 1))
    a, b = odom[k - 1], odom[k]
    f = 0.0 if b[0] == a[0] else float(np.clip((t - a[0]) / (b[0] - a[0]), 0, 1))
    qa, qb = a[4:8], b[4:8] * (1 if np.dot(a[4:8], b[4:8]) >= 0 else -1)
    q = qa * (1 - f) + qb * f
    return a[1:4] * (1 - f) + b[1:4] * f, q / np.linalg.norm(q)


def camera_world(pos, quat, mount_xyz, mount_rpy) -> tuple[np.ndarray, np.ndarray]:
    """The camera's world position and rotation (columns: forward, left, up)."""
    r_body = quat_mat(quat)
    return np.asarray(pos) + r_body @ np.asarray(mount_xyz), r_body @ rpy_mat(*mount_rpy)


def project_points(pts: np.ndarray, t_cam, r_cam, k: np.ndarray):
    """World points -> pixels, and their depth along the view; image right is the camera's -y."""
    c = (np.asarray(pts) - t_cam) @ r_cam  # camera frame: x forward, y left, z up
    depth = c[:, 0]
    with np.errstate(divide="ignore", invalid="ignore"):
        u = k[0, 2] - k[0, 0] * c[:, 1] / depth
        v = k[1, 2] - k[1, 1] * c[:, 2] / depth
    return np.stack([u, v], 1), depth


def outline(inst, n: int) -> np.ndarray:
    """The instance's ellipse at road level, as the surface baker paints it."""
    t = np.linspace(0, 2 * math.pi, n, endpoint=False)
    c, s = math.cos(inst.angle_rad), math.sin(inst.angle_rad)
    ex, ey = inst.length_m / 2 * np.cos(t), inst.width_m / 2 * np.sin(t)
    return np.stack([inst.x_m + ex * c - ey * s, inst.y_m + ex * s + ey * c, np.zeros(n)], 1)


def gt_boxes(road: Road, t_cam, r_cam, k, size, reach_m: float, n: int, behind_m: float):
    """[(id, cls, x1, y1, x2, y2)]: the box a perfect detector would draw round each instance.

    As sim/mujoco/survey.gt_boxes_by_id, with the camera's true pose: instances starting
    beyond `reach_m` ahead are skipped, and so is any with a point within `behind_m` of the
    camera plane, since part of it is under or behind the camera.
    """
    w, h = size
    out = []
    for i in road.instances:
        if i.bbox[2] <= t_cam[0] or i.bbox[0] >= t_cam[0] + reach_m:
            continue
        uv, depth = project_points(outline(i, n), t_cam, r_cam, k)
        if depth.min() <= behind_m:
            continue
        x1, y1 = np.clip(uv.min(0), 0, [w, h])
        x2, y2 = np.clip(uv.max(0), 0, [w, h])
        if x2 > x1 and y2 > y1:
            out.append((i.id, i.cls, float(x1), float(y1), float(x2), float(y2)))
    return out


def gate_row(k: np.ndarray) -> float:
    """The row where the design detect range meets flat road, for these intrinsics."""
    s = PROJECT["sim"]
    return project(
        PROJECT["edge"]["detect_range_m"],
        0.0,
        f=float(k[0, 0]),
        cx=float(k[0, 2]),
        cy=float(k[1, 2]),
        cam_h=s["cam_height_m"],
        pitch=math.radians(s["cam_pitch_deg"]),
    )[1]


def score(records: list[dict], road: Road, horizon: float, iou_min: float, km: float) -> dict:
    """Recall per class: any frame (raw boxes) and by confirmed track; false alarms per km."""
    by_id = {i.id: i for i in road.instances}
    seen, hit_any, hit_conf = set(), set(), set()
    tracks: dict[tuple, tuple[str, bool]] = {}
    for r in records:
        gts = r["gt"]
        seen.update(g[0] for g in gts if g[5] >= horizon)
        for d in r["raw"]:
            box = d["box"]
            hit_any.update(g[0] for g in gts if g[1] == d["cls"] and iou(box, g[2:]) > iou_min)
        for d in r["tracked"]:
            if not d["confirmed"]:
                continue
            mine = [g[0] for g in gts if g[1] == d["cls"] and iou(d["box"], g[2:]) > iou_min]
            hit_conf.update(mine)
            key = (d["model"], d["track"])
            tracks[key] = (d["cls"], tracks.get(key, (d["cls"], False))[1] or bool(mine))
    seen |= hit_any | hit_conf  # a hit instance was in view, whatever its own box said
    out = {}
    for c in CLASSES:
        n = sum(by_id[i].cls == c for i in seen)
        a = sum(by_id[i].cls == c for i in hit_any)
        h = sum(by_id[i].cls == c for i in hit_conf)
        fa = sum(1 for cls, ok in tracks.values() if cls == c and not ok)
        out[c] = {
            "in_view": n,
            "boxed_any_frame": a,
            "confirmed_hit": h,
            "false_alarm_tracks": fa,
            "false_alarms_per_km": round(fa / km, 2) if km else None,
            "ids_in_view": sorted(i for i in seen if by_id[i].cls == c),
            "ids_boxed_any_frame": sorted(i for i in hit_any if by_id[i].cls == c),
            "ids_confirmed_hit": sorted(i for i in hit_conf if by_id[i].cls == c),
        }
    return out


def wheel_offsets(car_cfg: dict) -> dict[str, np.ndarray]:
    """Each wheel's contact point under its centre, in the body frame at rest."""
    veh = car_cfg["vehicle"]
    z = -veh["cg_height_m"]
    return {
        f"{'front' if fx > 0 else 'rear'}_{'left' if sy > 0 else 'right'}": np.array(
            [fx * veh["wheelbase_m"] / 2, sy * veh["track_m"] / 2, z]
        )
        for fx in (1, -1)
        for sy in (1, -1)
    }


def _response(t, z, rpy, jt, travel, t0: float, ev: dict) -> dict | None:
    """Largest change in the window after t0 against the mean of the baseline before it."""
    base = (t >= t0 - ev["baseline_s"]) & (t < t0)
    after = (t >= t0) & (t <= t0 + ev["window_s"])
    jb = (jt >= t0 - ev["baseline_s"]) & (jt < t0)
    ja = (jt >= t0) & (jt <= t0 + ev["window_s"])
    if base.sum() < 2 or after.sum() < 2 or not ja.any() or not jb.any():
        return None
    d_rpy = np.degrees(rpy[after] - rpy[base].mean(0))
    leg = np.abs(travel[ja] - np.nanmean(travel[jb], axis=0))
    return {
        "heave_mm": round(float(np.abs(z[after] - z[base].mean()).max()) * 1e3, 1),
        "pitch_deg": round(float(np.abs(d_rpy[:, 1]).max()), 3),
        "roll_deg": round(float(np.abs(d_rpy[:, 0]).max()), 3),
        "travel_mm": round(float(np.nanmax(leg)) * 1e3, 1),
    }


def _stats(rows: list[dict]) -> dict:
    keys = ("heave_mm", "pitch_deg", "roll_deg", "travel_mm")
    return {
        k: {
            "max": max(r[k] for r in rows) if rows else None,
            "median": round(float(np.median([r[k] for r in rows])), 3) if rows else None,
        }
        for k in keys
    }


def ride_events(odom: np.ndarray, joints: list[dict], road: Road, look: dict, gz: dict) -> dict:
    """Body and suspension response where a wheel crosses a pothole, and on plain road.

    `odom` rows: t, x, y, z, qw, qx, qy, qz, forward speed. Only cruise counts (speed at least
    `min_speed_frac` of the design speed), so the launch's squat is not read as a pothole.
    The control samples the same statistic every `control_every_s` where no wheel is over a
    pothole, so a pothole's response can be told from the ride's own motion.
    """
    from sim.mujoco.relief import depth_at

    ev = gz["evaluate"]["ride"]
    t, z = odom[:, 0], odom[:, 3]
    cruise = odom[:, 8] >= ev["min_speed_frac"] * PROJECT["sim"]["speed_kmh"] / 3.6
    rpy = np.array([euler(quat_mat(q)) for q in odom[:, 4:8]])
    jt = np.array([j["t"] for j in joints])
    legs = list(wheel_offsets(gz))
    travel = np.array([[j.get(f"{w}_suspension", np.nan) for w in legs] for j in joints])
    over = np.zeros(len(t), bool)
    events = []
    rot = [quat_mat(q) for q in odom[:, 4:8]]
    for k, (name, off) in enumerate(wheel_offsets(gz).items()):
        pts = np.array([p + r @ off for p, r in zip(odom[:, 1:4], rot, strict=True)])
        depth = depth_at(road, look, pts[:, 0], pts[:, 1])
        deep = depth >= ev["wheel_drop_m"]
        over |= depth > 0
        for s in np.flatnonzero(deep & ~np.r_[False, deep[:-1]]):
            if not cruise[s]:
                continue
            r = _response(t, z, rpy, jt, travel[:, [k]], t[s], ev)
            if r is None:
                continue
            span = (t >= t[s]) & (t <= t[s] + ev["window_s"])
            events.append(
                {
                    "wheel": name,
                    "t_s": round(float(t[s]), 3),
                    "x_m": round(float(pts[s, 0]), 2),
                    "relief_depth_m": round(float(depth[span].max()), 4),
                    **r,
                }
            )
    control = []
    reach = ev["baseline_s"] + ev["window_s"]
    for t0 in np.arange(t[0] + reach, t[-1] - reach, ev["control_every_s"]):
        near = (t >= t0 - ev["baseline_s"]) & (t <= t0 + ev["window_s"])
        if over[near].any() or not cruise[near].all():
            continue
        r = _response(t, z, rpy, jt, travel, float(t0), ev)
        if r is not None:
            control.append(r)
    return {
        "events": len(events),
        "summary": _stats(events),
        "control_samples": len(control),
        "control": _stats(control),
        "list": events,
    }


def _draw(bgr, rec, colours, gt_rgb, scale, credit):
    """Ground truth thin white; raw boxes in their class colour; confirmed tracks green."""
    out = bgr.copy()
    font, white = cv2.FONT_HERSHEY_SIMPLEX, (255, 255, 255)
    for g in rec["gt"]:
        x1, y1, x2, y2 = (int(round(v)) for v in g[2:])
        cv2.rectangle(out, (x1, y1), (x2, y2), gt_rgb[::-1], 1)
    for d in rec["raw"]:
        x1, y1, x2, y2 = (int(round(v)) for v in d["box"])
        c = colours[d["cls"]]
        cv2.rectangle(out, (x1, y1), (x2, y2), c, 2)
        label = f"{d['model']} {d['cls']} {d['conf']:.2f}"
        cv2.putText(out, label, (x1, min(out.shape[0] - 24, y2 + 16)), font, scale, c, 2)
    for d in rec["tracked"]:
        if d["confirmed"]:
            x1, y1, x2, y2 = (int(round(v)) for v in d["box"])
            cv2.rectangle(out, (x1 - 3, y1 - 3), (x2 + 3, y2 + 3), colours["confirmed"], 2)
    head = f"Gazebo  camera x {rec['x_cam']:.1f} m  t {rec['stamp']:.2f} s"
    cv2.putText(out, head, (10, 24), font, scale, white, 2)
    legend = "white: truth  red: P  orange/yellow: B  green: confirmed"
    cv2.putText(out, legend, (10, 48), font, scale * 0.8, white, 1)
    cv2.putText(out, credit, (10, out.shape[0] - 10), font, scale * 0.6, white, 1)
    return out


def evaluate(world: Path, limit: int | None = None, drive_name: str = "drive") -> dict:
    from ultralytics import YOLO

    from certain_road.core.device import available_device

    sys.path.insert(0, str(repo_root() / "scripts"))
    from eval_video import confirm_step

    gz = load_gz()
    look = load_config(gz["look"])
    ev, drv = gz["evaluate"], look["drive"]
    car = yaml.safe_load(CAR.read_text())
    drive = world / drive_name
    road = Road.from_json((world / "ground_truth.json").read_text())
    summary = json.loads((drive / "summary.json").read_text())
    frames = [json.loads(line) for line in (drive / "frames.jsonl").open()]
    if limit:
        frames = frames[:limit]
    odom = np.array([json.loads(line)[:9] for line in (drive / "odom.jsonl").open()])
    joints = [json.loads(line) for line in (drive / "joints.jsonl").open()]
    info = summary["camera_info"]
    k = np.array(info["k"]).reshape(3, 3)
    size = (info["w"], info["h"])
    horizon = gate_row(k)
    reach = PROJECT["edge"]["detect_range_m"] + ev["reach_margin_m"]
    device = available_device(VIDEO["device"])
    weights = {m: str(repo_root() / VIDEO["models"][m]) for m in ("P", "B")}
    raw_models = {m: YOLO(w) for m, w in weights.items()}
    track_models = {m: YOLO(w) for m, w in weights.items()}
    confirmers: dict[str, dict] = {m: {} for m in weights}
    records = []
    log = (drive / "detections.jsonl").open("w")
    for f in frames:
        pos, quat = interp_pose(odom, f["stamp"])
        t_cam, r_cam = camera_world(pos, quat, car["camera_xyz"], car["camera_rpy"])
        bgr = cv2.imread(str(drive / f["file"]))
        rec = {
            "i": f["i"],
            "stamp": f["stamp"],
            "x_cam": round(float(t_cam[0]), 3),
            "gt": gt_boxes(
                road,
                t_cam,
                r_cam,
                k,
                size,
                reach,
                look["survey"]["gt_outline_points"],
                ev["behind_m"],
            ),
            "raw": [],
            "tracked": [],
        }
        for m in ("P", "B"):
            res = raw_models[m].predict(bgr, conf=VIDEO["conf"], device=device, verbose=False)[0]
            b = res.boxes
            rec["raw"] += [
                {
                    "model": m,
                    "cls": res.names[c],
                    "conf": round(s, 4),
                    "box": [round(v, 1) for v in xyxy],
                }
                for c, s, xyxy in zip(
                    b.cls.int().tolist(), b.conf.tolist(), b.xyxy.tolist(), strict=True
                )
                if res.names[c] in drv["classes_from"][m]
            ]
            res = track_models[m].track(
                bgr,
                persist=True,
                tracker=VIDEO["tracker"],
                conf=VIDEO["conf"],
                device=device,
                verbose=False,
            )[0]
            b = res.boxes
            ids = b.id.int().tolist() if b.id is not None else [None] * len(b)
            rows = [
                {
                    "model": m,
                    "cls": res.names[c],
                    "conf": round(s, 4),
                    "box": [round(v, 1) for v in xyxy],
                    "track": tid,
                }
                for c, s, xyxy, tid in zip(
                    b.cls.int().tolist(), b.conf.tolist(), b.xyxy.tolist(), ids, strict=True
                )
                if res.names[c] in drv["classes_from"][m]
            ]
            confirmed = confirm_step(
                confirmers[m],
                [(d["track"], d["box"][3]) for d in rows if d["track"] is not None],
                horizon,
                **VIDEO["confirm"],
            )
            for d in rows:
                d["confirmed"] = d["track"] in confirmed and d["box"][3] >= horizon
            rec["tracked"] += rows
        log.write(json.dumps(rec) + "\n")
        records.append(rec)
    log.close()
    km = (records[-1]["x_cam"] - records[0]["x_cam"]) / 1000 if records else 0.0
    result = {
        "world": world.name,
        "frames": len(records),
        "km": round(km, 4),
        "camera": {"w": size[0], "h": size[1], "fx": float(k[0, 0]), "gate_row": round(horizon, 1)},
        "conf": VIDEO["conf"],
        "iou_min": look["end"]["iou_min"],
        "device": device,
        "detection": score(records, road, horizon, look["end"]["iou_min"], km),
        "ride": ride_events(odom, joints, road, look, gz),
        "drive": {k2: v for k2, v in summary.items() if k2 != "samples"},
    }
    (drive / "eval.json").write_text(json.dumps(result, indent=1))
    evidence(world, drive, records, result, gz, look)
    return result


def evidence(
    world: Path, drive: Path, records: list[dict], result: dict, gz: dict, look: dict
) -> None:
    """A few annotated frames and a short clip, under runs/gazebo/evidence_<world>/."""
    ev = gz["evaluate"]
    tag = "" if drive.name == "drive" else f"_{drive.name}"
    out = world.parent / f"evidence_{world.name}{tag}"
    out.mkdir(parents=True, exist_ok=True)
    colours = {k: tuple(v) for k, v in look["drive"]["colours_bgr"].items()}
    credit = " ".join(look["credits"].split())
    pots = set(result["detection"]["pothole"]["ids_boxed_any_frame"])

    def boxed(rec):
        return sum(
            1
            for g in rec["gt"]
            if g[0] in pots
            and any(
                d["cls"] == "pothole" and iou(d["box"], g[2:]) > result["iou_min"]
                for d in rec["raw"]
            )
        )

    order = sorted(records, key=lambda r: (-boxed(r), r["i"]))
    picked: list[dict] = []
    for r in order:  # spread them along the road: no two within the clip's length
        if len(picked) == ev["annotated_frames"]:
            break
        if all(abs(r["x_cam"] - p["x_cam"]) > ev["frame_spacing_m"] for p in picked):
            picked.append(r)
    for r in sorted(picked, key=lambda r: r["i"]):
        bgr = cv2.imread(str(drive / f"frames/{r['i']:06d}.jpg"))
        cv2.imwrite(
            str(out / f"frame_{r['i']:06d}.png"),
            _draw(bgr, r, colours, ev["gt_rgb"], ev["font_scale"], credit),
        )
    hz = result["drive"]["camera_hz_sim"] or gz["camera"]["rate_hz"]
    n = int(round(ev["clip_s"] * hz))
    in_view = np.array(
        [
            sum(g[1] == "pothole" and g[5] >= result["camera"]["gate_row"] for g in r["gt"])
            for r in records
        ]
    )
    start = int(np.argmax(np.convolve(in_view, np.ones(n), "valid"))) if len(records) > n else 0
    clip = records[start : start + n]
    h, w = cv2.imread(str(drive / f"frames/{clip[0]['i']:06d}.jpg")).shape[:2]
    vw = cv2.VideoWriter(str(out / "clip.mp4"), cv2.VideoWriter_fourcc(*"mp4v"), hz, (w, h))
    for r in clip:
        bgr = cv2.imread(str(drive / f"frames/{r['i']:06d}.jpg"))
        vw.write(_draw(bgr, r, colours, ev["gt_rgb"], ev["font_scale"], credit))
    vw.release()


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--world", type=Path, required=True)
    ap.add_argument("--limit", type=int, help="score only the first N frames")
    ap.add_argument("--drive", default="drive", help="the drive folder inside the world")
    ap.add_argument(
        "--evidence-only", action="store_true", help="redraw frames and clip from a scored drive"
    )
    args = ap.parse_args()
    if args.evidence_only:
        world = args.world.resolve()
        drive = world / args.drive
        gz = load_gz()
        records = [json.loads(line) for line in (drive / "detections.jsonl").open()]
        result = json.loads((drive / "eval.json").read_text())
        evidence(world, drive, records, result, gz, load_config(gz["look"]))
        return
    r = evaluate(args.world.resolve(), args.limit, args.drive)
    det = {
        c: {k: v for k, v in d.items() if not k.startswith("ids_")}
        for c, d in r["detection"].items()
    }
    print(
        json.dumps(
            {
                "detection": det,
                "ride": {k: v for k, v in r["ride"].items() if k != "list"},
            },
            indent=1,
        )
    )


if __name__ == "__main__":
    main()
