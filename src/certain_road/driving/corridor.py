"""Is a detection in the robot's driving path?

Two design decisions this module encodes (see docs/superpowers/plans/
2026-09-05-day5-corridor-sim.md and docs/DECISIONS.md D049/D050):

1. The driving corridor is not the survey ROI. They are different trapezoids
   serving different purposes (see `configs/driving/corridor.yaml`) and must
   never share a config file.

2. Proximity is the box's bottom edge, not its height -- see the
   `proximity()` function added in Task B.

Corridor/box overlap is computed by clipping the detection box against the
corridor polygon with Sutherland-Hodgman and measuring area with the shoelace
formula -- both textbook, dependency-free techniques. No `shapely`.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np
import yaml

from certain_road.artifacts.schema import Detection
from certain_road.core.paths import repo_root

CORRIDOR_CONFIG_PATH = repo_root() / "configs" / "driving" / "corridor.yaml"


@dataclass(frozen=True)
class Corridor:
    """Driving corridor geometry and decision thresholds, in image fractions.

    NOT the survey ROI (D049/D050): this answers "where will my wheels go",
    narrower and purpose-built for the drive pipeline. The survey ROI answers
    "what road can the camera see" for `vision_density` and lives in its own
    config so the two pipelines can never accidentally share one trapezoid.
    """

    center_x: float
    top_y: float
    top_half_width: float
    bottom_y: float
    bottom_half_width: float
    min_overlap: float


def load_corridor(path: Path) -> Corridor:
    """Load a `Corridor` from a YAML file shaped like `configs/driving/corridor.yaml`.

    Raises `FileNotFoundError` if `path` does not exist -- a missing corridor
    config must fail loudly, not silently fall back to a hardcoded default.
    """
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"corridor config not found: {path}")
    raw = yaml.safe_load(path.read_text())
    return Corridor(
        center_x=raw["center_x"],
        top_y=raw["top_y"],
        top_half_width=raw["top_half_width"],
        bottom_y=raw["bottom_y"],
        bottom_half_width=raw["bottom_half_width"],
        min_overlap=raw["min_overlap"],
    )


def corridor_polygon(corridor: Corridor, img_w: int, img_h: int) -> np.ndarray:
    """The corridor trapezoid in pixel coordinates for an `img_w` x `img_h` frame.

    Returns a (4, 2) array ordered top-left, top-right, bottom-right,
    bottom-left. The trapezoid widens from `top_*` (near the horizon) to
    `bottom_*` (at the camera) -- the perspective projection of two parallel
    wheel tracks converging toward the vanishing point.
    """
    cx = corridor.center_x * img_w
    top_y_px = corridor.top_y * img_h
    bottom_y_px = corridor.bottom_y * img_h
    top_hw_px = corridor.top_half_width * img_w
    bottom_hw_px = corridor.bottom_half_width * img_w
    return np.array(
        [
            [cx - top_hw_px, top_y_px],
            [cx + top_hw_px, top_y_px],
            [cx + bottom_hw_px, bottom_y_px],
            [cx - bottom_hw_px, bottom_y_px],
        ]
    )


def _box_polygon(det: Detection) -> np.ndarray:
    return np.array(
        [
            [det.x1, det.y1],
            [det.x2, det.y1],
            [det.x2, det.y2],
            [det.x1, det.y2],
        ]
    )


def _polygon_area(polygon: np.ndarray) -> float:
    """Shoelace formula. Assumes a simple (non-self-intersecting) polygon."""
    if len(polygon) < 3:
        return 0.0
    x = polygon[:, 0]
    y = polygon[:, 1]
    return 0.5 * abs(np.dot(x, np.roll(y, -1)) - np.dot(y, np.roll(x, -1)))


def _cross2d(u: np.ndarray, v: np.ndarray) -> float:
    """2D cross product (the scalar z-component). `numpy.cross` dropped
    support for 2-vectors, so this is spelled out directly."""
    return u[0] * v[1] - u[1] * v[0]


def _inside_edge(p: np.ndarray, edge: np.ndarray, a: np.ndarray) -> bool:
    """Whether `p` is on the "inside" half-plane of the directed edge `a -> a+edge`.

    Correct for a convex polygon wound the way `corridor_polygon` winds it
    (top-left, top-right, bottom-right, bottom-left) -- see the plan doc.
    """
    return _cross2d(edge, p - a) >= 0


def _line_intersection(p1: np.ndarray, p2: np.ndarray, a: np.ndarray, b: np.ndarray) -> np.ndarray:
    """Intersection of segment p1->p2 with the infinite line through a->b."""
    x1, y1 = p1
    x2, y2 = p2
    x3, y3 = a
    x4, y4 = b
    denom = (x1 - x2) * (y3 - y4) - (y1 - y2) * (x3 - x4)
    if denom == 0:
        return p2  # parallel; degenerate, keep the endpoint
    t = ((x1 - x3) * (y3 - y4) - (y1 - y3) * (x3 - x4)) / denom
    return np.array([x1 + t * (x2 - x1), y1 + t * (y2 - y1)])


def _clip_polygon(subject: np.ndarray, clip: np.ndarray) -> np.ndarray:
    """Sutherland-Hodgman: clip `subject` against the convex polygon `clip`.

    `clip`'s vertices must be wound so that `corridor_polygon`'s order
    (top-left, top-right, bottom-right, bottom-left) is "inside positive" --
    see the derivation in the plan doc. Returns the intersection polygon's
    vertices (empty if there is no overlap).
    """
    output = list(subject)
    n = len(clip)
    for i in range(n):
        if not output:
            break
        a, b = clip[i], clip[(i + 1) % n]
        edge = b - a

        input_list = output
        output = []
        for j in range(len(input_list)):
            current = input_list[j]
            previous = input_list[j - 1]
            current_in = _inside_edge(current, edge, a)
            previous_in = _inside_edge(previous, edge, a)
            if current_in:
                if not previous_in:
                    output.append(_line_intersection(previous, current, a, b))
                output.append(current)
            elif previous_in:
                output.append(_line_intersection(previous, current, a, b))
    return np.array(output) if output else np.empty((0, 2))


def overlap_fraction(det: Detection, corridor: Corridor) -> float:
    """Fraction of `det`'s box area that lies inside the corridor polygon."""
    box = _box_polygon(det)
    box_area = _polygon_area(box)
    if box_area <= 0:
        return 0.0
    polygon = corridor_polygon(corridor, det.img_w, det.img_h)
    clipped = _clip_polygon(box, polygon)
    return float(_polygon_area(clipped) / box_area)


def in_path(det: Detection, corridor: Corridor, *, min_overlap: float) -> bool:
    """Whether `det` overlaps the corridor by at least `min_overlap`."""
    return overlap_fraction(det, corridor) >= min_overlap
