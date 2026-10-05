"""The live survey: every 5 m sample scored through certain_road.survey, segment by segment.

Nothing here scores anything itself. It decides which boxes a sample counts, then hands
them to the real code:

- **Which boxes (D006).** A sample counts the boxes whose base lies in a fixed ROI, the
  `edge.sample_every_m` strip of the driving lane starting `survey.roi_near_m` ahead. Samples
  are that far apart, so the strips tile the road and no damage is counted twice. The base is
  found with `core.geometry.ground_point`, the IPM.
- **Segments.** `survey.segment.segment_drive` groups the samples, 10 to a segment
  (`scoring.segment_m / edge.sample_every_m`), and counts the classes in each.
- **Score.** Each class's footprints come from `scoring.box_footprint_m2`. Those go through
  `segment_distress` and `deduct_value` with the project's weights, then
  `vision_estimated_pci` and `band`.
- **Reference.** The ground truth goes through the same path. Each instance is projected into
  the sample as the box a perfect detector would draw, then counted and scored exactly like a
  detection. Predicted and reference PCI then share all of their geometry, which is what
  makes D006 valid.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import date

import numpy as np
import pandas as pd
import yaml

from certain_road.core.geometry import ground_point, project
from certain_road.core.paths import repo_root
from certain_road.survey import scoring
from certain_road.survey.segment import CLASS_COLUMNS, segment_drive
from sim.mujoco.road import CLASSES, Road
from sim.mujoco.scene import design_camera

PROJECT = yaml.safe_load((repo_root() / "configs/project.yaml").read_text())
Box = tuple[str, float, float, float, float]  # class, x1, y1, x2, y2 in pixels


def survey_camera(cam: dict) -> scoring.Camera:
    """The calibration the survey assumes: the design camera, without per-frame noise."""
    return scoring.Camera(
        f=cam["f"], cx=cam["w"] / 2, cy=cam["h"] / 2, cam_h=cam["height"], pitch=cam["pitch"]
    )


def ipm_kw(camera: scoring.Camera) -> dict:
    return {
        "f": camera.f,
        "cx": camera.cx,
        "cy": camera.cy,
        "cam_h": camera.cam_h,
        "pitch": camera.pitch,
    }


def roi(cfg: dict) -> tuple[float, float, float]:
    """(near, far, half-width) of D006's ROI in metres, relative to the camera."""
    p = PROJECT
    near = cfg["survey"]["roi_near_m"]
    return near, near + p["edge"]["sample_every_m"], p["scoring"]["lane_width_m"] / 2


def base_point(box: Box, camera: scoring.Camera) -> tuple[float, float] | None:
    """Ground point under the bottom centre of a box, by the IPM."""
    _, x1, _, x2, y2 = box
    return ground_point((x1 + x2) / 2, y2, **ipm_kw(camera))


def in_roi(box: Box, camera: scoring.Camera, cfg: dict) -> bool:
    g = base_point(box, camera)
    if g is None:
        return False
    near, far, half = roi(cfg)
    return near <= g[0] < far and abs(g[1]) <= half


def gt_boxes(road: Road, x_cam: float, cam: dict, cfg: dict) -> list[Box]:
    """The box a perfect detector would draw round each instance, from the camera at x_cam.

    Projects the instance's ellipse, the shape the surface baker paints, and clips the box to
    the frame. Only instances that could reach the ROI are projected.
    """
    camera = survey_camera(cam)
    _, far, _ = roi(cfg)
    t = np.linspace(0, 2 * math.pi, cfg["survey"]["gt_outline_points"], endpoint=False)
    out = []
    for i in road.instances:
        if i.bbox[2] <= x_cam or i.bbox[0] >= x_cam + far + 1.0:
            continue
        c, s = math.cos(i.angle_rad), math.sin(i.angle_rad)
        ex, ey = i.length_m / 2 * np.cos(t), i.width_m / 2 * np.sin(t)
        fwd = i.x_m + ex * c - ey * s - x_cam
        left = i.y_m + ex * s + ey * c - road.drive_lane_y
        if fwd.min() <= 0.1:  # part of it is under or behind the camera: never in the ROI
            continue
        uv = np.array([project(a, b, **ipm_kw(camera)) for a, b in zip(fwd, left, strict=True)])
        x1, y1 = np.clip(uv.min(0), 0, [cam["w"], cam["h"]])
        x2, y2 = np.clip(uv.max(0), 0, [cam["w"], cam["h"]])
        if x2 > x1 and y2 > y1:
            out.append((i.cls, float(x1), float(y1), float(x2), float(y2)))
    return out


def score_boxes(boxes: list[Box], camera: scoring.Camera, segment_m: float) -> dict:
    """One segment's vision-estimated PCI from its counted boxes, by the real scoring code."""
    p = PROJECT["scoring"]
    distress, deducts = {}, {}
    for c in CLASSES:
        fp = [scoring.box_footprint_m2(*b[1:], camera) for b in boxes if b[0] == c]
        value, unit = scoring.segment_distress(
            fp, segment_m=segment_m, lane_width_m=p["lane_width_m"]
        )
        distress[c] = (round(value, 4), unit)
        deducts[c] = scoring.deduct_value(value, p["deduct_weights"][c])
    pci = scoring.vision_estimated_pci(deducts)
    return {"pci": pci, "band": scoring.band(pci), "distress": distress, "deducts": deducts}


@dataclass
class SegmentResult:
    index: int
    x0_m: float  # ground the segment scores, along the road
    x1_m: float
    n_samples: int
    counts: dict[str, int]  # from segment_drive
    vision_estimated_pci: float
    band: str
    distress: dict[str, tuple[float, str]]
    pci_ref: float  # reference PCI: the ground truth through the same path
    band_ref: str
    distress_ref: dict[str, tuple[float, str]]


@dataclass
class Survey:
    """Feed it survey samples in order; it closes a segment every `per_segment` samples."""

    road: Road
    cfg: dict
    cam: dict = field(default_factory=design_camera)
    samples: list[dict] = field(default_factory=list)
    segments: list[SegmentResult] = field(default_factory=list)

    def __post_init__(self):
        p = PROJECT
        self.camera = survey_camera(self.cam)
        self.step_m = p["edge"]["sample_every_m"]
        self.per_segment = round(p["scoring"]["segment_m"] / self.step_m)

    def add(
        self, frame_id: int, x_m: float, t_s: float, dets: list[Box | tuple]
    ) -> SegmentResult | None:
        """One sample's detections, (class, score, x1, y1, x2, y2). Returns a segment it closes."""
        kept = [d for d in dets if in_roi((d[0], *d[2:]), self.camera, self.cfg)]
        counted = [(d[0], *d[2:]) for d in kept]
        scores = [d[1] for d in kept]
        ref = [
            b
            for b in gt_boxes(self.road, x_m, self.cam, self.cfg)
            if in_roi(b, self.camera, self.cfg)
        ]
        self.samples.append(
            {
                "frame_id": str(frame_id),
                "x_m": x_m,
                "t_s": t_s,
                "boxes": counted,
                "scores": scores,
                "ref": ref,
            }
        )
        if len(self.samples) % self.per_segment == 0:
            return self._close()
        return None

    def finish(self) -> SegmentResult | None:
        """Score the trailing partial segment over its own length; segment_drive keeps it too."""
        if len(self.samples) % self.per_segment:
            return self._close()
        return None

    def running(self) -> dict | None:
        """The segment in progress, scored so far against a full segment's length."""
        k = len(self.samples) % self.per_segment
        if k == 0:
            return None
        part = self.samples[-k:]
        s = score_boxes(
            [b for x in part for b in x["boxes"]], self.camera, self.per_segment * self.step_m
        )
        return {**s, "n_samples": k, "index": len(self.segments)}

    def table(self) -> pd.DataFrame:
        """segment_drive over every sample so far: the real grouping and counts."""
        log = pd.DataFrame(
            {
                "frame_id": [s["frame_id"] for s in self.samples],
                "timestamp_s": [s["t_s"] for s in self.samples],
                "survey_date": [date.today()] * len(self.samples),
            }
        )
        dets = pd.DataFrame(
            [
                {"frame_id": s["frame_id"], "class_name": b[0], "score": sc}
                for s in self.samples
                for b, sc in zip(s["boxes"], s["scores"], strict=True)
            ],
            columns=["frame_id", "class_name", "score"],
        )
        return segment_drive(dets, log, frames_per_segment=self.per_segment)

    def _close(self) -> SegmentResult:
        row = self.table().iloc[len(self.segments)]
        ids = [s["frame_id"] for s in self.samples]
        block = self.samples[ids.index(row["first_frame_id"]) : ids.index(row["last_frame_id"]) + 1]
        near, far, _ = roi(self.cfg)
        seg_m = row["n_frames"] * self.step_m
        got = score_boxes([b for s in block for b in s["boxes"]], self.camera, seg_m)
        ref = score_boxes([b for s in block for b in s["ref"]], self.camera, seg_m)
        res = SegmentResult(
            index=len(self.segments),
            x0_m=block[0]["x_m"] + near,
            x1_m=block[-1]["x_m"] + far,
            n_samples=int(row["n_frames"]),
            counts={c: int(row[CLASS_COLUMNS[c]]) for c in CLASSES},
            vision_estimated_pci=round(got["pci"], 2),
            band=got["band"],
            distress=got["distress"],
            pci_ref=round(ref["pci"], 2),
            band_ref=ref["band"],
            distress_ref=ref["distress"],
        )
        self.segments.append(res)
        return res
