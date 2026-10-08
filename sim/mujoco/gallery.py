"""Every confirmed pothole and crack of a drive: its frame, its box, and where it is on the road.

    uv run python -m sim.mujoco.gallery --preset poor --seed 0

Reads a finished run (runs/mujoco/<preset>_seed<seed>_v2/) and writes `gallery.json` and
`gallery/*.jpg` beside its logs, for the survey report (scripts/survey_environments.py).

- **One entry per confirmed track** (D075), from both models under D082's channels: potholes
  from Model P, cracks from Model B. The picture is the frame where the track's confidence
  peaked while confirmed, with that frame's box drawn.
- **Frames are re-rendered, not saved during the drive**, so any finished run qualifies and
  the drive loop is unchanged. The render is a function of the camera position, except for
  one sensor-noise offset drawn per frame; `Camera.skip_frames` replays that stream, so the
  frame is the one the models saw. `--verify-frames` checks this: it re-detects some survey
  samples with plain `predict`, as the drive did, and compares the boxes with the log.
- **Location by the IPM.** The bottom centre of each confirmed box goes through
  `core.geometry.ground_point` with the design camera, as the survey's ROI test does (D089),
  and the median over the track's confirmed frames is its place: metres along the road, and
  metres left of the centre line. That point is the near edge of the damage as the camera
  sees it, on a flat-road assumption; pitch and roll noise move it, and the error against
  the ground truth is reported, not corrected.
- **Matched against the ground truth** with the end screen's own rule
  (`evaluate.match_tracks`). A track that hit no instance of its class is a false alarm; the
  nearest instance of any class is recorded, because D092 found pothole false alarms sitting
  on crack patches.

What this is not: a count of damage. Tracks are not instances (D075), and the survey's
vision-estimated PCI comes from the 5 m samples, not from these tracks.
"""

from __future__ import annotations

import argparse
import copy
import json
import math
import statistics
import time
from pathlib import Path

import cv2
import numpy as np

from certain_road.core.geometry import ground_point
from certain_road.core.paths import repo_root
from sim.mujoco.evaluate import iou, match_tracks
from sim.mujoco.road import Road
from sim.mujoco.scene import design_camera
from sim.mujoco.survey import in_roi, ipm_kw, survey_camera

Key = tuple[str, int]


def track_frames(records: list[dict]) -> dict[Key, list[dict]]:
    """Every frame in which each track was confirmed: frame index, camera x, score, box."""
    out: dict[Key, list[dict]] = {}
    for r in records:
        for d in r["dets"]:
            if d["confirmed"]:
                out.setdefault((d["model"], d["track"]), []).append(
                    {
                        "frame": r["frame"],
                        "x_cam_m": r["x_m"],
                        "score": d["score"],
                        "box": [d["x1"], d["y1"], d["x2"], d["y2"]],
                    }
                )
    return out


def base_ground(box, x_cam: float, cam: dict, drive_lane_y: float) -> tuple[float, float] | None:
    """(metres along the road, metres left of the centre line) under the box's bottom centre."""
    g = ground_point((box[0] + box[2]) / 2, box[3], **ipm_kw(survey_camera(cam)))
    if g is None:
        return None
    return x_cam + g[0], drive_lane_y + g[1]


def lane_of(lateral_m: float, lane_width_m: float) -> str:
    """Keep left (India): the vehicle drives the left lane; y is left of the centre line."""
    if 0.0 <= lateral_m <= lane_width_m:
        return "left lane (driving)"
    if -lane_width_m <= lateral_m < 0.0:
        return "right lane (oncoming)"
    return "left verge" if lateral_m > 0 else "right verge"


def segment_of(chainage_m: float, segments: list[dict]) -> int | None:
    """The survey segment whose scored ground holds this chainage, if any."""
    for s in segments:
        if s["x0_m"] <= chainage_m < s["x1_m"]:
            return s["index"]
    return None


def bbox_distance(x: float, y: float, bbox) -> float:
    """Distance in metres from a ground point to an instance's footprint box (0 inside)."""
    dx = max(bbox[0] - x, 0.0, x - bbox[2])
    dy = max(bbox[1] - y, 0.0, y - bbox[3])
    return math.hypot(dx, dy)


def counted_in_survey(
    model: str, cls: str, track: int, records: list[dict], cfg: dict, cam: dict
) -> bool:
    """Did a survey sample's own box for this object fall in D006's ROI?

    The survey's boxes come from plain `predict`, not from the tracker, so the track is
    matched to them by overlap in the sampled frame, with the end screen's IoU rule.
    """
    camera = survey_camera(cam)
    for r in records:
        if not r["sampled"]:
            continue
        mine = [d for d in r["dets"] if d["model"] == model and d["track"] == track]
        for d in mine:
            box = (d["x1"], d["y1"], d["x2"], d["y2"])
            for s in r["survey"]:
                if s["model"] != model or s["cls"] != cls:
                    continue
                sbox = (s["x1"], s["y1"], s["x2"], s["y2"])
                if iou(box, sbox) > cfg["end"]["iou_min"] and in_roi((cls, *sbox), camera, cfg):
                    return True
    return False


def summarise_tracks(
    road: Road, records: list[dict], segments: list[dict], cfg: dict, cam: dict | None = None
) -> list[dict]:
    """One dict per confirmed track: what, how sure, where, and whether the truth agrees."""
    cam = cam or design_camera()
    _, _, matched = match_tracks(road, records, cfg, cam)
    by_id = {i.id: i for i in road.instances}
    out = []
    for (model, track), frames in sorted(track_frames(records).items(), key=_first_frame):
        cls, hit_ids = matched[(model, track)]
        best = max(frames, key=lambda f: (f["score"], -f["frame"]))
        points = [
            p for f in frames if (p := base_ground(f["box"], f["x_cam_m"], cam, road.drive_lane_y))
        ]
        loc = None
        if points:
            x = statistics.median(p[0] for p in points)
            y = statistics.median(p[1] for p in points)
            near = min(road.instances, key=lambda i: bbox_distance(x, y, i.bbox), default=None)
            loc = {
                "chainage_m": round(x, 2),
                "lateral_m": round(y, 2),
                "lane": lane_of(y, road.lane_width_m),
                "segment": segment_of(x, segments),
                "error_to_match_m": (
                    round(min(bbox_distance(x, y, by_id[g].bbox) for g in hit_ids), 2)
                    if hit_ids
                    else None
                ),
                "nearest_instance": (
                    {
                        "id": near.id,
                        "cls": near.cls,
                        "distance_m": round(bbox_distance(x, y, near.bbox), 2),
                    }
                    if near is not None
                    else None
                ),
            }
        out.append(
            {
                "model": model,
                "cls": cls,
                "track": track,
                "hit_ids": sorted(hit_ids),
                "false_alarm": not hit_ids,
                "confirmed_frames": len(frames),
                "first_x_cam_m": frames[0]["x_cam_m"],
                "best": best,
                "location": loc,
                "counted_in_survey": counted_in_survey(model, cls, track, records, cfg, cam),
            }
        )
    return out


def _first_frame(item) -> tuple[int, str, int]:
    (model, track), frames = item
    return frames[0]["frame"], model, track


def crop_with_box(bgr: np.ndarray, box, colour, g: dict) -> tuple[np.ndarray, np.ndarray]:
    """(crop around the box, whole frame), both with the box drawn, both downscaled."""
    img = bgr.copy()
    x1, y1, x2, y2 = (int(round(v)) for v in box)
    cv2.rectangle(img, (x1, y1), (x2, y2), colour, g["box_px"], cv2.LINE_AA)
    pad = max(g["min_pad_px"], int(g["context"] * max(x2 - x1, y2 - y1)))
    h, w = img.shape[:2]
    crop = img[max(0, y1 - pad) : min(h, y2 + pad), max(0, x1 - pad) : min(w, x2 + pad)]
    scale = g["crop_px"] / max(crop.shape[:2])
    crop = cv2.resize(crop, None, fx=scale, fy=scale, interpolation=cv2.INTER_AREA)
    fs = g["frame_width_px"] / w
    frame = cv2.resize(img, None, fx=fs, fy=fs, interpolation=cv2.INTER_AREA)
    return crop, frame


def drive_camera(road: Road, cfg: dict):
    """The scene and camera exactly as `drive.Driver` builds them."""
    from sim.mujoco.camera import Camera
    from sim.mujoco.scene import build

    model, cam = build(road, cfg)
    live = copy.deepcopy(cfg)
    live["camera_effects"].update(cfg["drive"]["render"])
    return Camera(model, cam, live, road.seed, road.drive_lane_y), cam


def replay(camera, wanted: dict[int, float]):
    """Yield (frame index, BGR) for the wanted frames, in order, exactly as the drive saw them."""
    drawn = 0
    for k in sorted(wanted):
        camera.skip_frames(k - drawn)
        yield k, camera.frame(wanted[k])
        drawn = k + 1


def verify_frames(records: list[dict], n: int) -> list[int]:
    """Survey samples with logged survey boxes, spread over the drive, to re-detect."""
    with_boxes = [r["frame"] for r in records if r["sampled"] and r["survey"]]
    if not with_boxes or n <= 0:
        return []
    picks = np.linspace(0, len(with_boxes) - 1, min(n, len(with_boxes))).round().astype(int)
    return sorted({with_boxes[i] for i in picks})


def redetect(bgr: np.ndarray, models: dict, cfg: dict) -> list[tuple]:
    """Plain predict, as drive.Driver._sample does it, with D082's channels."""
    from sim.mujoco.drive import VIDEO, keep

    out = []
    for name, model in models.items():
        r = model.predict(bgr, conf=VIDEO["conf"], device=VIDEO["device"], verbose=False)[0]
        b = r.boxes
        for c, s, xyxy in zip(b.cls.int().tolist(), b.conf.tolist(), b.xyxy.tolist(), strict=True):
            if keep(name, r.names[c], cfg):
                out.append((name, r.names[c], round(s, 4), *[round(v, 1) for v in xyxy]))
    return out


def compare(logged: list[dict], again: list[tuple]) -> dict:
    """How far the re-detected survey boxes are from the logged ones."""

    def order(row: tuple) -> tuple:
        return row[0], row[1], row[3], row[4]  # model, class, x1, y1: stable under tiny drift

    old = sorted(
        ((d["model"], d["cls"], d["score"], d["x1"], d["y1"], d["x2"], d["y2"]) for d in logged),
        key=order,
    )
    again = sorted(again, key=order)
    same_count = len(old) == len(again) and all(
        a[:2] == b[:2] for a, b in zip(old, again, strict=False)
    )
    diffs = [
        max(abs(p - q) for p, q in zip(a[3:], b[3:], strict=True))
        for a, b in zip(old, again, strict=False)
    ]
    return {
        "logged": len(old),
        "redetected": len(again),
        "same_boxes": same_count,
        "max_px_diff": round(max(diffs), 3) if diffs else None,
        "max_score_diff": (
            round(max(abs(a[2] - b[2]) for a, b in zip(old, again, strict=False)), 4)
            if old and again
            else None
        ),
    }


def build_gallery(run_dir: Path, road: Road, cfg: dict, n_verify: int) -> dict:
    g = cfg["gallery"]
    t0 = time.perf_counter()
    records = [json.loads(line) for line in (run_dir / "detections.jsonl").open()]
    segments = json.loads((run_dir / "survey.json").read_text())["segments"]
    tracks = summarise_tracks(road, records, segments, cfg)
    wanted = {t["best"]["frame"]: t["best"]["x_cam_m"] for t in tracks}
    checks = verify_frames(records, n_verify)
    by_frame = {r["frame"]: r for r in records}
    wanted.update({k: by_frame[k]["x_m"] for k in checks})
    t1 = time.perf_counter()
    camera, _ = drive_camera(road, cfg)
    t2 = time.perf_counter()
    models = {}
    if checks:
        from ultralytics import YOLO

        from sim.mujoco.drive import VIDEO

        models = {m: YOLO(str(repo_root() / VIDEO["models"][m])) for m in ("P", "B")}
    out_dir = run_dir / g["dir"]
    out_dir.mkdir(parents=True, exist_ok=True)
    colours = cfg["drive"]["colours_bgr"]
    verification = []
    by_best: dict[int, list[dict]] = {}
    for t in tracks:
        by_best.setdefault(t["best"]["frame"], []).append(t)
    for k, bgr in replay(camera, wanted):
        if k in checks:
            v = compare(by_frame[k]["survey"], redetect(bgr, models, cfg))
            verification.append({"frame": k, "x_m": by_frame[k]["x_m"], **v})
        for t in by_best.get(k, []):
            crop, frame = crop_with_box(bgr, t["best"]["box"], colours[t["cls"]], g)
            stem = f"{t['model']}_{t['cls']}_{t['track']}"
            q = [cv2.IMWRITE_JPEG_QUALITY, g["jpeg_quality"]]
            cv2.imwrite(str(out_dir / f"{stem}.jpg"), crop, q)
            cv2.imwrite(str(out_dir / f"{stem}_frame.jpg"), frame, q)
            t["crop"] = f"{g['dir']}/{stem}.jpg"
            t["frame"] = f"{g['dir']}/{stem}_frame.jpg"
    result = {
        "preset": road.preset,
        "seed": road.seed,
        "look": cfg.get("look", "v1"),
        "frames_logged": len(records),
        "tracks": tracks,
        "replay": {
            "method": (
                "re-rendered at the logged camera position with the drive's camera settings; "
                "the per-frame sensor-noise stream skipped to the logged frame index"
            ),
            "verification": verification,
        },
        "timing_s": {
            "summarise": round(t1 - t0, 1),
            "scene_build": round(t2 - t1, 1),
            "render_and_write": round(time.perf_counter() - t2, 1),
        },
    }
    (run_dir / "gallery.json").write_text(json.dumps(result, indent=1))
    return result


def main() -> None:
    from sim.mujoco.demo import PRESETS, make_road
    from sim.mujoco.road import load_config

    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--preset", choices=PRESETS, required=True)
    ap.add_argument("--seed", type=int, required=True)
    ap.add_argument("--look")
    ap.add_argument(
        "--verify-frames",
        type=int,
        help="survey samples to re-detect against the log (default: gallery.verify_frames)",
    )
    args = ap.parse_args()
    look = args.look or load_config()["default_look"]
    road, cfg = make_road(args.preset, args.seed, look)
    tag = "" if look == "v1" else f"_{look}"
    run_dir = repo_root() / cfg["out_dir"] / f"{args.preset}_seed{args.seed}{tag}"
    saved = Road.from_json((run_dir / "ground_truth.json").read_text())
    if saved != road:
        raise SystemExit(f"{run_dir}: ground truth differs from a fresh {args.preset} road")
    n = cfg["gallery"]["verify_frames"] if args.verify_frames is None else args.verify_frames
    res = build_gallery(run_dir, road, cfg, n)
    fa = sum(t["false_alarm"] for t in res["tracks"])
    print(
        f"{len(res['tracks'])} confirmed tracks ({fa} false alarms) -> {run_dir / 'gallery.json'}"
    )
    print(json.dumps({"verification": res["replay"]["verification"], **res["timing_s"]}, indent=1))


if __name__ == "__main__":
    main()
