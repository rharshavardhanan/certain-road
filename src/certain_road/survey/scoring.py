"""T12 — evaluation-segment health from detections: vision density to a PCI-style score.

**This is a proxy, not ASTM D6433.** It follows the *structure* of Ibragimov et
al. (Sensors 2024) — a monotone deduct that grows with the logarithm of
distress extent — but it does not use D6433's deduct curves, and it performs no
iterative corrected-deduct-value step. The output is a **vision-estimated PCI**:
comparable between evaluation segments surveyed the same way, and not
interchangeable with an engineer's D6433 rating.

`vision_density` is deliberately not called density: ASTM density is distress
area over a physically measured pavement area. This is a projected image
footprint over a nominal lane rectangle, which is a different quantity that
happens to behave similarly.

Where an inverse-perspective footprint is unavailable — no calibrated camera, or
boxes whose bottom edge falls above the horizon — the score falls back to counts
per 100 m and says so, because silently substituting a different unit is how a
dashboard ends up comparing two things that are not the same.
"""

import math
from dataclasses import dataclass

from certain_road.core.geometry import ground_point, haversine_m

BANDS = [
    (86, 100, "Good"), (71, 85, "Satisfactory"), (56, 70, "Fair"), (41, 55, "Poor"),
    (26, 40, "Very Poor"), (11, 25, "Serious"), (0, 10, "Failed"),
]


@dataclass(frozen=True)
class Camera:
    f: float
    cx: float
    cy: float
    cam_h: float
    pitch: float


def band(score: float) -> str:
    for low, high, name in BANDS:
        if low <= score <= high:
            return name
    raise ValueError(f"score {score} outside 0-100")


def segment_index(distances_m: list[float], segment_m: float) -> list[int]:
    """Which evaluation segment each cumulative distance falls in."""
    return [int(d // segment_m) for d in distances_m]


def cumulative_distance_m(lats: list[float], lons: list[float]) -> list[float]:
    out = [0.0]
    for i in range(1, len(lats)):
        out.append(out[-1] + haversine_m(lats[i - 1], lons[i - 1], lats[i], lons[i]))
    return out


def box_footprint_m2(
    x1: float, y1: float, x2: float, y2: float, camera: Camera
) -> float | None:
    """Ground area of a detection, from the inverse-perspective map of its base.

    Width comes from the two bottom corners; depth from the bottom edge to the
    box's own top edge along the centreline. Both can fail — a box whose top edge
    projects above the horizon has no ground intersection — and failure returns
    None rather than a guess, so the caller can fall back to counting.
    """
    left = ground_point(x1, y2, f=camera.f, cx=camera.cx, cy=camera.cy,
                        cam_h=camera.cam_h, pitch=camera.pitch)
    right = ground_point(x2, y2, f=camera.f, cx=camera.cx, cy=camera.cy,
                         cam_h=camera.cam_h, pitch=camera.pitch)
    far = ground_point((x1 + x2) / 2, y1, f=camera.f, cx=camera.cx, cy=camera.cy,
                       cam_h=camera.cam_h, pitch=camera.pitch)
    near = ground_point((x1 + x2) / 2, y2, f=camera.f, cx=camera.cx, cy=camera.cy,
                        cam_h=camera.cam_h, pitch=camera.pitch)
    if left is None or right is None or far is None or near is None:
        return None
    width = abs(left[1] - right[1])
    depth = abs(far[0] - near[0])
    return width * depth


def vision_density(
    footprint_m2: float, *, segment_m: float, lane_width_m: float
) -> float:
    """Projected distress footprint as a percentage of the nominal lane area."""
    area = segment_m * lane_width_m
    return 0.0 if area <= 0 else footprint_m2 / area * 100.0


def deduct_value(vision_density_pct: float, weight: float) -> float:
    """`w_c · log10(1 + vision_density)` — monotone, and zero at zero distress.

    Logarithmic because the first few square metres of damage matter far more
    than the next few: a segment going from sound to cracked is a bigger change
    in condition than one already-bad segment getting worse.
    """
    return weight * math.log10(1.0 + max(0.0, vision_density_pct))


def vision_estimated_pci(deducts: dict[str, float]) -> float:
    """100 minus the summed deducts, clipped to [0, 100]."""
    return max(0.0, min(100.0, 100.0 - sum(deducts.values())))


def robust_vision_density(
    vision_density_pct: float, alpha: float, *, certified: bool = True
) -> float:
    """Inflate pothole density by 1/(1-alpha) using T10's certified miss rate.

    If the detector is certified to miss at most alpha of potholes, then what it
    found is at most (1-alpha) of what is there, so dividing recovers a bound on
    the truth rather than a point estimate. Only ever apply this with an alpha a
    conformal procedure actually certified: using a guessed alpha produces a
    number that looks conservative and guarantees nothing.
    """
    if not certified:
        raise ValueError("robust scoring requires a certified alpha from T10")
    if not 0.0 <= alpha < 1.0:
        raise ValueError(f"alpha must be in [0, 1), got {alpha}")
    return vision_density_pct / (1.0 - alpha)
