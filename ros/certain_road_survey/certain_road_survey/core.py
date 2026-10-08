"""The survey from a camera topic, without ROS: odometry, frames and detections in, report out.

`survey_node` feeds this class from topics; tests feed it by hand. It decides which frames
are survey samples, which boxes each sample counts, when a segment closes, and writes the
same artifacts and report as the MuJoCo survey (scripts/survey_environments.py).

- **Samples by distance (D006).** A frame is a sample once the camera has passed the next
  mark, one every `edge.sample_every_m`. Its place on the road comes from odometry at the
  frame's own stamp, interpolated, because detections arrive later than the image.
- **The ROI is fixed on the road, not on the camera.** A frame rarely lands exactly on its
  mark, so the counted strip is shifted back by the overshoot: the sample at mark m counts
  boxes whose base lies m + roi_near to m + roi_near + step along the road. Consecutive
  samples then tile the road exactly, as the MuJoCo survey's exact positions do. The rule
  itself is `certain_road.survey.sample.in_roi`, the one the MuJoCo survey is pinned to.
- **Scored** by `certain_road.survey.sample.score_boxes`, `segment_m / sample_every_m`
  samples to a segment, a trailing partial segment scored over its own length.
- **Every counted box is pictured** with its frame, box, class, confidence, the model D082
  assigns its class, and its place: chainage and metres left of the vehicle's path.

What it cannot do: check anything against ground truth (a camera topic carries none), so
the report shows no recall, no false alarms and no reference PCI, and says so. A mark the
camera passed without a frame (a stall) is skipped and counted, never invented.
"""

from __future__ import annotations

import bisect
import json
import math
from collections import deque
from dataclasses import dataclass
from datetime import date
from pathlib import Path

import cv2
import numpy as np

from certain_road.dashboard.survey_report import (
    MODEL_OF,
    Pricing,
    RoadRun,
    build_report,
    write,
)
from certain_road.survey import sample, scoring
from certain_road.survey.rsl import RslConfig

Det = tuple[str, float, float, float, float, float]  # class, score, x1, y1, x2, y2


@dataclass(frozen=True)
class Pose:
    t: float
    x: float
    y: float
    yaw: float


class Odometry:
    """Recent poses, and the camera's chainage at any stamp between them."""

    def __init__(self, mode: str, forward_m: float, maxlen: int):
        if mode not in ("world_x", "path"):
            raise ValueError(f"chainage must be world_x or path, got {mode!r}")
        self.mode, self.forward_m = mode, forward_m
        self.ts: deque[float] = deque(maxlen=maxlen)
        self.cs: deque[float] = deque(maxlen=maxlen)
        self._last: tuple[float, float] | None = None
        self._travel = 0.0

    def add(self, p: Pose) -> None:
        if self.ts and p.t <= self.ts[-1]:
            return  # out of order or repeated: the history must stay sorted
        cx = p.x + self.forward_m * math.cos(p.yaw)
        cy = p.y + self.forward_m * math.sin(p.yaw)
        if self._last is not None:
            self._travel += math.hypot(cx - self._last[0], cy - self._last[1])
        self._last = (cx, cy)
        self.ts.append(p.t)
        self.cs.append(cx if self.mode == "world_x" else self._travel)

    def chainage_at(self, t: float) -> float | None:
        """Interpolated chainage at t; the newest pose after it; None before the history."""
        if not self.ts or t < self.ts[0]:
            return None
        if t >= self.ts[-1]:
            return self.cs[-1]
        i = bisect.bisect_right(self.ts, t)
        t0, t1, c0, c1 = self.ts[i - 1], self.ts[i], self.cs[i - 1], self.cs[i]
        return c0 + (c1 - c0) * (t - t0) / (t1 - t0)


class RosSurvey:
    def __init__(
        self,
        cfg: dict,
        project: dict,
        rsl_cfg: RslConfig,
        report_cfg: dict,
        out_dir: Path,
        *,
        label: str,
        simulated: bool,
        run_dir_label: str,
    ):
        self.cfg, self.report_cfg, self.rsl_cfg = cfg, report_cfg, rsl_cfg
        self.out_dir, self.label, self.simulated = out_dir, label, simulated
        self.run_dir_label = run_dir_label
        self.step = float(project["edge"]["sample_every_m"])
        sc = project["scoring"]
        self.segment_m, self.lane_w = float(sc["segment_m"]), float(sc["lane_width_m"])
        self.weights = dict(sc["deduct_weights"])
        self.per_segment = round(self.segment_m / self.step)
        a = project["allocation"]
        self.pricing = Pricing(
            mobilisation_cost=float(a["mobilisation_cost"]),
            cost_per_m2=float(a["cost_per_m2"]),
            budget_frac=float(cfg["budget_frac"]),
            worst_share=a["worst_k"] / a["n_segments"],
        )
        cam = cfg["camera"]
        self.odometry = Odometry(
            cfg["chainage"], float(cam["forward_of_odom_m"]), cfg["odom_history"]
        )
        self.camera: scoring.Camera | None = None
        self.next_mark: float | None = None
        self.samples: list[dict] = []
        self.segments: list[dict] = []
        self.items: list[dict] = []
        self.images: dict[str, bytes] = {}
        self.skipped_marks = 0
        self.frames_seen = 0

    # -- inputs ---------------------------------------------------------------------------

    def set_intrinsics(self, f: float, cx: float, cy: float) -> None:
        cam = self.cfg["camera"]
        self.camera = scoring.Camera(
            f=f, cx=cx, cy=cy, cam_h=float(cam["height_m"]), pitch=math.radians(cam["pitch_deg"])
        )

    def pose(self, p: Pose) -> None:
        self.odometry.add(p)

    def frame(self, t: float, bgr: np.ndarray | None, dets: list[Det]) -> dict | None:
        """One frame with its detections. Returns a segment if this sample closed one."""
        self.frames_seen += 1
        c = self.odometry.chainage_at(t)
        if c is None or self.camera is None:
            return None
        if self.next_mark is None:  # the first mark at or after the start
            self.next_mark = math.ceil(c / self.step) * self.step
        if c < self.next_mark:
            return None
        mark = math.floor(c / self.step) * self.step
        self.skipped_marks += round((mark - self.next_mark) / self.step)
        self.next_mark = mark + self.step
        near = self.cfg["roi_near_m"] + mark - c  # the strip, fixed on the road
        counted = [
            d
            for d in dets
            if sample.in_roi(
                (d[0], *d[2:]),
                self.camera,
                near_m=near,
                far_m=near + self.step,
                half_width_m=self.lane_w / 2,
            )
        ]
        k = len(self.samples)
        for j, d in enumerate(counted):
            self._picture(k, j, t, c, bgr, d)
        self.samples.append({"k": k, "t": t, "mark_m": mark, "chainage_m": c, "dets": counted})
        if len(self.samples) % self.per_segment == 0:
            return self._close()
        return None

    def finish(self) -> dict | None:
        if len(self.samples) % self.per_segment:
            return self._close()
        return None

    # -- scoring and pictures ---------------------------------------------------------------

    def _close(self) -> dict:
        n = len(self.samples) % self.per_segment or self.per_segment
        block = self.samples[-n:]
        boxes = [(d[0], *d[2:]) for s in block for d in s["dets"]]
        # each sample's own camera, by its overshoot, would move its footprints by centimetres;
        # the camera position is not needed for area, only for which boxes count
        got = sample.score_boxes(
            boxes,
            self.camera,
            segment_m=n * self.step,
            lane_width_m=self.lane_w,
            weights=self.weights,
        )
        near = self.cfg["roi_near_m"]
        seg = {
            "index": len(self.segments),
            "x0_m": block[0]["mark_m"] + near,
            "x1_m": block[-1]["mark_m"] + near + self.step,
            "n_samples": n,
            "counts": {c: sum(b[0] == c for b in boxes) for c in self.weights},
            "vision_estimated_pci": round(got["pci"], 2),
            "band": got["band"],
            "distress": got["distress"],
            "area_m2": round(got["area_m2"], 4),
            "survey_date": date.today().isoformat(),
        }
        self.segments.append(seg)
        return seg

    def _picture(self, k: int, j: int, t: float, c: float, bgr, d: Det) -> None:
        cls, score, x1, y1, x2, y2 = d
        g = sample.base_point((cls, x1, y1, x2, y2), self.camera)
        stem = f"s{k:04d}_{j}_{cls}"
        item = {
            "model": MODEL_OF.get(cls, "?"),
            "cls": cls,
            "track": None,
            "hit_ids": [],
            "false_alarm": None,  # no ground truth on a camera topic
            "best": {
                "frame": k,
                "t_s": t,
                "x_cam_m": round(c, 2),
                "score": score,
                "box": [x1, y1, x2, y2],
            },
            "location": {
                "chainage_m": round(c + g[0], 2),
                "lateral_m": round(g[1], 2),
                "lateral_ref": "the vehicle's path",
                "lane": "driving lane (the survey ROI)",
                "segment": len(self.segments),
            },
            "counted_in_survey": True,
        }
        if bgr is not None:
            gc = self.cfg["gallery"]
            crop, frame = crop_with_box(bgr, (x1, y1, x2, y2), gc["colours_bgr"].get(cls), gc)
            q = [cv2.IMWRITE_JPEG_QUALITY, gc["jpeg_quality"]]
            for key, img in (("crop", crop), ("frame", frame)):
                ok, enc = cv2.imencode(".jpg", img, q)
                if ok:
                    rel = f"gallery/{stem}{'' if key == 'crop' else '_frame'}.jpg"
                    self.images[rel] = enc.tobytes()
                    item[key] = rel
        self.items.append(item)

    # -- outputs ------------------------------------------------------------------------------

    def write(self, stamp: dict) -> Path | None:
        """survey.json, gallery.json, the pictures and the report, from what is closed so far."""
        if not self.segments:
            return None
        self.out_dir.mkdir(parents=True, exist_ok=True)
        (self.out_dir / "gallery").mkdir(exist_ok=True)
        for rel, data in self.images.items():
            p = self.out_dir / rel
            if not p.exists():
                p.write_bytes(data)
        survey = {
            "segments": self.segments,
            "samples": len(self.samples),
            "skipped_marks": self.skipped_marks,
            "frames_seen": self.frames_seen,
        }
        (self.out_dir / "survey.json").write_text(json.dumps(survey, indent=1))
        gallery = {
            "tracks": self.items,
            "replay": {"method": "saved live from the camera topic", "verification": []},
        }
        (self.out_dir / "gallery.json").write_text(json.dumps(gallery, indent=1))
        road = RoadRun(
            label=self.label,
            preset="ros",
            seed=0,
            look="",
            length_m=self.segments[-1]["x1_m"] - self.segments[0]["x0_m"],
            run_dir=self.run_dir_label,
            segments=self.segments,
            detection=None,
            gallery=gallery,
            images=self.images,
            timing={},
            simulated=self.simulated,
        )
        page, data = build_report([road], self.rsl_cfg, self.pricing, self.report_cfg, stamp)
        data["ros"] = {k: survey[k] for k in ("samples", "skipped_marks", "frames_seen")}
        html_path, _ = write(page, data, self.out_dir)
        return html_path


def crop_with_box(bgr: np.ndarray, box, colour, g: dict) -> tuple[np.ndarray, np.ndarray]:
    """(crop around the box, whole frame), both with the box drawn, both downscaled."""
    img = bgr.copy()
    x1, y1, x2, y2 = (int(round(v)) for v in box)
    cv2.rectangle(img, (x1, y1), (x2, y2), tuple(colour or (255, 255, 255)), g["box_px"])
    pad = max(g["min_pad_px"], int(g["context"] * max(x2 - x1, y2 - y1)))
    h, w = img.shape[:2]
    crop = img[max(0, y1 - pad) : min(h, y2 + pad), max(0, x1 - pad) : min(w, x2 + pad)]
    scale = g["crop_px"] / max(crop.shape[:2])
    crop = cv2.resize(crop, None, fx=scale, fy=scale, interpolation=cv2.INTER_AREA)
    fs = g["frame_width_px"] / w
    frame = cv2.resize(img, None, fx=fs, fy=fs, interpolation=cv2.INTER_AREA)
    return crop, frame
