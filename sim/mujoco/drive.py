"""Drive the design camera down the road and detect with the real models, frame by frame.

Each frame is rendered (camera.Camera), handed to ultralytics as BGR, and tracked by Model P
and Model B with ByteTrack under the video lane's settings (configs/eval/video.yaml).

- **D082 channels.** Potholes come from P only and cracks from B only. B's pothole channel
  is discarded, so the two are never summed.
- **D075 confirmation.** A track is confirmed by `confirm_step` from scripts/eval_video.py,
  imported rather than copied: the same ID present in 3 of the last 5 frames.
- **The gate.** The video lane gates at a hand-set fraction of the frame because its footage
  has no camera model. The simulator has one, so the gate is the row where the design detect
  range (`edge.detect_range_m`) meets the road, from `core.geometry.project`.
- **Survey samples.** One frame in every `frames_per_sample` is a survey sample, every
  `edge.sample_every_m` (D006). Those are the frames step 3 scores.
"""

from __future__ import annotations

import copy
import json
import sys
import time
from collections.abc import Iterator
from dataclasses import asdict, dataclass
from pathlib import Path

import numpy as np
import yaml

from certain_road.core.geometry import project
from certain_road.core.paths import repo_root
from sim.mujoco.road import Road

sys.path.insert(0, str(repo_root() / "scripts"))
from eval_video import confirm_step  # noqa: E402  D075, one definition

VIDEO = yaml.safe_load((repo_root() / "configs/eval/video.yaml").read_text())
PROJECT = yaml.safe_load((repo_root() / "configs/project.yaml").read_text())


@dataclass
class Det:
    model: str
    cls: str
    score: float
    x1: float
    y1: float
    x2: float
    y2: float
    track: int | None
    confirmed: bool = False


@dataclass
class FrameRecord:
    frame: int
    x_m: float
    t_s: float
    sampled: bool
    dets: list[Det]
    ms: dict


def keep(model: str, cls: str, cfg: dict) -> bool:
    """D082: which model's outputs count for which class."""
    return cls in cfg["drive"]["classes_from"][model]


def gate_row(cam: dict) -> float:
    """Image row where the design detect range meets the road; boxes above it are gated."""
    r = PROJECT["edge"]["detect_range_m"]
    _, v = project(
        r,
        0.0,
        f=cam["f"],
        cx=cam["w"] / 2,
        cy=cam["h"] / 2,
        cam_h=cam["height"],
        pitch=cam["pitch"],
    )
    return v


def frame_positions(length_m: float, cfg: dict) -> tuple[list[float], list[bool]]:
    """Camera positions along the road, and which of them are survey samples."""
    k = cfg["drive"]["frames_per_sample"]
    step = PROJECT["edge"]["sample_every_m"] / k
    n = int((length_m - cfg["drive"]["end_margin_m"]) / step)
    return [round(i * step, 6) for i in range(n)], [i % k == 0 for i in range(n)]


class Driver:
    def __init__(self, road: Road, cfg: dict):
        from ultralytics import YOLO

        from sim.mujoco.camera import Camera
        from sim.mujoco.scene import build

        self.road, self.cfg = road, cfg
        model, self.cam = build(road, cfg)
        live = copy.deepcopy(cfg)
        live["camera_effects"].update(cfg["drive"]["render"])
        self.camera = Camera(model, self.cam, live, road.seed, road.drive_lane_y)
        self.models = {m: YOLO(str(repo_root() / VIDEO["models"][m])) for m in ("P", "B")}
        self.confirmers: dict[str, dict] = {m: {} for m in self.models}
        self.horizon = gate_row(self.cam)
        self.xs, self.sampled = frame_positions(road.length_m, cfg)

    def frames(self) -> Iterator[tuple[FrameRecord, np.ndarray]]:
        speed = self.cam["speed_mps"]
        for k, x in enumerate(self.xs):
            t0 = time.perf_counter()
            bgr = self.camera.frame(x)
            t1 = time.perf_counter()
            dets: list[Det] = []
            ms = {"render": (t1 - t0) * 1e3}
            for name, model in self.models.items():
                t2 = time.perf_counter()
                res = model.track(
                    bgr,
                    persist=True,
                    tracker=VIDEO["tracker"],
                    conf=VIDEO["conf"],
                    device=VIDEO["device"],
                    verbose=False,
                )[0]
                ms[name] = (time.perf_counter() - t2) * 1e3
                b = res.boxes
                ids = b.id.int().tolist() if b.id is not None else [None] * len(b)
                rows = [
                    Det(name, res.names[c], round(s, 4), *[round(v, 1) for v in xyxy], tid)
                    for c, s, xyxy, tid in zip(
                        b.cls.int().tolist(), b.conf.tolist(), b.xyxy.tolist(), ids, strict=True
                    )
                    if keep(name, res.names[c], self.cfg)
                ]
                confirmed = confirm_step(
                    self.confirmers[name],
                    [(d.track, d.y2) for d in rows if d.track is not None],
                    self.horizon,
                    **VIDEO["confirm"],
                )
                for d in rows:
                    d.confirmed = d.track in confirmed and d.y2 >= self.horizon
                dets += rows
            yield FrameRecord(k, x, round(x / speed, 4), self.sampled[k], dets, ms), bgr


def run(road: Road, cfg: dict, out_dir: Path, show=None, until_m: float | None = None) -> dict:
    """Drive the whole road, logging every frame. `show(record, bgr, driver)` False stops it."""
    out_dir.mkdir(parents=True, exist_ok=True)
    road.save(out_dir / "ground_truth.json")
    drv = Driver(road, cfg)
    log = (out_dir / "detections.jsonl").open("w")
    times: dict[str, list[float]] = {}
    n = 0
    tracks: dict[str, set] = {}
    t_start = time.perf_counter()
    for rec, bgr in drv.frames():
        if until_m is not None and rec.x_m > until_m:
            break
        log.write(json.dumps({**asdict(rec), "dets": [asdict(d) for d in rec.dets]}) + "\n")
        for k, v in rec.ms.items():
            times.setdefault(k, []).append(v)
        for d in rec.dets:
            if d.confirmed:
                tracks.setdefault(f"{d.model}:{d.cls}", set()).add(d.track)
        n += 1
        if show is not None and show(rec, bgr, drv) is False:
            break
    log.close()
    summary = {
        "preset": road.preset,
        "seed": road.seed,
        "frames": n,
        "sampled_frames": sum(drv.sampled[:n]),
        "metres": round(drv.xs[n - 1], 2) if n else 0,
        "wall_s": round(time.perf_counter() - t_start, 1),
        "gate_row": round(drv.horizon, 1),
        "ms_p50": {k: round(float(np.median(v)), 1) for k, v in times.items()},
        "confirmed_tracks": {k: len(v) for k, v in sorted(tracks.items())},
        "ground_truth": {
            c: sum(i.cls == c for i in road.instances)
            for c in ("linear_crack", "alligator_crack", "pothole")
        },
    }
    (out_dir / "drive_summary.json").write_text(json.dumps(summary, indent=1))
    return summary
