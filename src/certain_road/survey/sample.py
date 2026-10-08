"""D006 survey samples from any calibrated camera: which boxes a sample counts, and a score.

**Why it exists.** The MuJoCo demo decides which boxes a 5 m sample counts and scores a
segment from them in `sim/mujoco/survey.py`, a simulator module. A survey fed by any other
camera (a ROS topic from Gazebo, a car) needs the same two rules without importing a
simulator, so they live here, in the survey stage, and a test pins this module to the
simulator's version box for box.

- **Which boxes (D006, D089).** A sample counts a box whose base centre, put on the ground by
  `core.geometry.ground_point`, lies in the ROI: the strip `near_m`-`far_m` ahead and within
  `half_width_m` of the camera's own path. Samples spaced `far_m - near_m` apart tile the road,
  so nothing is counted twice.
- **Score.** Per class, each counted box's ground footprint (`scoring.box_footprint_m2`) goes
  through `segment_distress`, `deduct_value` with the project's weights, then
  `vision_estimated_pci` and `band`.

**What it is not.** Not a detector and not a tracker; it trusts the boxes it is given. The
flat-road IPM is the dominant error (core/geometry.py), and it assumes the camera's height and
pitch are known.
"""

from __future__ import annotations

from collections.abc import Sequence

from certain_road.core.geometry import ground_point
from certain_road.survey import scoring

Box = tuple[str, float, float, float, float]  # class, x1, y1, x2, y2 in pixels


def _kw(camera: scoring.Camera) -> dict:
    return {
        "f": camera.f,
        "cx": camera.cx,
        "cy": camera.cy,
        "cam_h": camera.cam_h,
        "pitch": camera.pitch,
    }


def base_point(box: Box, camera: scoring.Camera) -> tuple[float, float] | None:
    """(metres ahead, metres left) of the ground under the bottom centre of a box."""
    _, x1, _, x2, y2 = box
    return ground_point((x1 + x2) / 2, y2, **_kw(camera))


def in_roi(
    box: Box, camera: scoring.Camera, *, near_m: float, far_m: float, half_width_m: float
) -> bool:
    g = base_point(box, camera)
    return g is not None and near_m <= g[0] < far_m and abs(g[1]) <= half_width_m


def score_boxes(
    boxes: Sequence[Box],
    camera: scoring.Camera,
    *,
    segment_m: float,
    lane_width_m: float,
    weights: dict[str, float],
) -> dict:
    """One segment's vision-estimated PCI from its counted boxes, by the scoring code."""
    distress, deducts, area = {}, {}, 0.0
    for c, w in weights.items():
        fp = [scoring.box_footprint_m2(*b[1:], camera) for b in boxes if b[0] == c]
        area += sum(f for f in fp if f is not None)
        value, unit = scoring.segment_distress(fp, segment_m=segment_m, lane_width_m=lane_width_m)
        distress[c] = (round(float(value), 4), unit)
        deducts[c] = scoring.deduct_value(value, w)
    pci = scoring.vision_estimated_pci(deducts)
    return {
        "pci": pci,
        "band": scoring.band(pci),
        "distress": distress,
        "deducts": deducts,
        "area_m2": area,
    }
