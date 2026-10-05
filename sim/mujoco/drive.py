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
  `edge.sample_every_m` (D006). Each one is detected again with plain `predict`, no tracker,
  by its own P and B, and scored by `survey.Survey`.
- **Drift.** On each sample a third copy of B scores the frame exactly as `model.val` scored
  india_val (`exp_video_extent.val_mode_scorer`), for D078's CUSUM martingale against that
  bag, as D080 did. The scorer's NMS patch is process-wide, so it is held to its own calls,
  where it cannot change what the trackers see.
"""

from __future__ import annotations

import copy
import json
import sys
import time
from collections.abc import Iterator
from dataclasses import asdict, dataclass, field
from pathlib import Path

import numpy as np
import yaml

from certain_road.core.geometry import project
from certain_road.core.paths import repo_root
from sim.mujoco.road import Road
from sim.mujoco.survey import SegmentResult, Survey

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
    survey: list[Det] = field(default_factory=list)  # sampled frames only: plain predict
    drift: dict | None = None  # sampled frames only: score, log_m, alarmed
    closed: SegmentResult | None = None  # the segment this sample completed, if any


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


def drift_scorer(model):
    """exp_video_extent's val-mode scorer, with its process-wide NMS patch held to its calls."""
    import ultralytics.utils.nms as nms
    from exp_video_extent import val_mode_scorer

    plain = nms.non_max_suppression
    score = val_mode_scorer(model)
    multi, nms.non_max_suppression = nms.non_max_suppression, plain

    def scoped(img: np.ndarray) -> float:
        nms.non_max_suppression = multi
        try:
            return score(img)[0]
        finally:
            nms.non_max_suppression = plain

    return scoped


def frame_positions(length_m: float, cfg: dict) -> tuple[list[float], list[bool]]:
    """Camera positions along the road, and which of them are survey samples."""
    k = cfg["drive"]["frames_per_sample"]
    step = PROJECT["edge"]["sample_every_m"] / k
    n = int((length_m - cfg["drive"]["end_margin_m"]) / step)
    return [round(i * step, 6) for i in range(n)], [i % k == 0 for i in range(n)]


class Driver:
    def __init__(self, road: Road, cfg: dict):
        from exp_drift import frame_scores
        from ultralytics import YOLO

        from certain_road.assess.drift import DriftMartingale
        from sim.mujoco.camera import Camera
        from sim.mujoco.scene import build

        self.road, self.cfg = road, cfg
        model, self.cam = build(road, cfg)
        live = copy.deepcopy(cfg)
        live["camera_effects"].update(cfg["drive"]["render"])
        self.camera = Camera(model, self.cam, live, road.seed, road.drive_lane_y)
        weights = {m: str(repo_root() / VIDEO["models"][m]) for m in ("P", "B")}
        self.models = {m: YOLO(w) for m, w in weights.items()}
        self.survey_models = {m: YOLO(w) for m, w in weights.items()}  # no tracker state
        self.drift_score = drift_scorer(YOLO(weights["B"]))
        dv, dr = VIDEO["drift"], PROJECT["drift"]
        self.drift = DriftMartingale(
            frame_scores(repo_root() / dv["reference_predictions"], dv["reference_split"]),
            eps=dr["eps"],
            alarm_threshold=dv["cusum_threshold"],
            seed=road.seed,
            cusum=True,
        )
        self.survey = Survey(road, cfg, self.cam)
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
            rec = FrameRecord(k, x, round(x / speed, 4), self.sampled[k], dets, ms)
            if rec.sampled:
                self._sample(rec, bgr)
            yield rec, bgr

    def _sample(self, rec: FrameRecord, bgr: np.ndarray) -> None:
        """A 5 m survey sample: plain detection for the survey, val-mode B for drift."""
        t0 = time.perf_counter()
        for name, model in self.survey_models.items():
            r = model.predict(bgr, conf=VIDEO["conf"], device=VIDEO["device"], verbose=False)[0]
            b = r.boxes
            rec.survey += [
                Det(name, r.names[c], round(s, 4), *[round(v, 1) for v in xyxy], None)
                for c, s, xyxy in zip(
                    b.cls.int().tolist(), b.conf.tolist(), b.xyxy.tolist(), strict=True
                )
                if keep(name, r.names[c], self.cfg)
            ]
        rec.closed = self.survey.add(
            rec.frame,
            rec.x_m,
            rec.t_s,
            [(d.cls, d.score, d.x1, d.y1, d.x2, d.y2) for d in rec.survey],
        )
        t1 = time.perf_counter()
        s = self.drift_score(bgr)
        self.drift.update(s)
        rec.drift = {
            "score": round(s, 5),
            "log_m": round(self.drift.log_m, 4),
            "alarmed": self.drift.alarmed,
        }
        rec.ms["survey"], rec.ms["drift"] = (t1 - t0) * 1e3, (time.perf_counter() - t1) * 1e3


def run(road: Road, cfg: dict, out_dir: Path, show=None, until_m: float | None = None) -> dict:
    """Drive the whole road, logging every frame. `show(record, bgr, driver)` False stops it."""
    out_dir.mkdir(parents=True, exist_ok=True)
    road.save(out_dir / "ground_truth.json")
    drv = Driver(road, cfg)
    log = (out_dir / "detections.jsonl").open("w")
    times: dict[str, list[float]] = {}
    n = 0
    tracks: dict[str, set] = {}
    trace: list[dict] = []
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
        if rec.drift is not None:
            trace.append({"x_m": rec.x_m, **rec.drift})
        n += 1
        if show is not None and show(rec, bgr, drv) is False:
            break
    log.close()
    drv.survey.finish()
    alarm = next((d["x_m"] for d in trace if d["alarmed"]), None)
    survey = {
        "segments": [asdict(s) for s in drv.survey.segments],
        "drift": {
            "threshold_log": round(drv.drift.log_threshold, 4),
            "alarm_m": alarm,
            "trace": trace,
        },
    }
    (out_dir / "survey.json").write_text(json.dumps(survey, indent=1))
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
        "segments": [
            [s.index, s.vision_estimated_pci, s.band, s.pci_ref, s.band_ref]
            for s in drv.survey.segments
        ],
        "drift_alarm_m": alarm,
        "ground_truth": {
            c: sum(i.cls == c for i in road.instances)
            for c in ("linear_crack", "alligator_crack", "pothole")
        },
    }
    (out_dir / "drive_summary.json").write_text(json.dumps(summary, indent=1))
    return summary
