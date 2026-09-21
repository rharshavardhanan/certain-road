"""T12 — ground-plane geometry: inverse perspective mapping and GPS helpers.

`ground_point` is the inverse-perspective map: given a pixel, where on the road
surface is it? It assumes a **flat ground plane** at a known camera height and
pitch. That assumption is the dominant error term — a crest, a dip or a camber
puts the answer out by more than any pixel noise — so range is validated against
ground truth in T13 rather than trusted.

This lives in `core` because both the simulator and the survey pipeline need it
and `import-linter` forbids them importing each other. It depends on nothing.

`sim/project.py` parameterises the same camera by field of view rather than focal
length; the two agree under `f = (img_w / 2) / tan(hfov / 2)`, which
`test_geometry.py` pins.
"""

import math

# Below this the ray is parallel to or above the ground plane and never meets it.
MIN_DENOMINATOR = 1e-6
EARTH_RADIUS_M = 6_371_008.8


def ground_point(
    u: float, v: float, *, f: float, cx: float, cy: float, cam_h: float, pitch: float
) -> tuple[float, float] | None:
    """Pixel (u, v) -> ground (X forward, Y left) in metres, or None.

    The camera is pitched down by `pitch` and image y increases downward, so a
    row above the horizon gives a non-positive denominator and no intersection.
    """
    x = (u - cx) / f
    y = (v - cy) / f
    den = math.sin(pitch) + y * math.cos(pitch)
    if den <= MIN_DENOMINATOR:
        return None
    t = cam_h / den
    return t * (math.cos(pitch) - y * math.sin(pitch)), -t * x


def project(
    forward: float, left: float, *, f: float, cx: float, cy: float, cam_h: float, pitch: float
) -> tuple[float, float] | None:
    """Ground (X forward, Y left) -> pixel (u, v). Exact inverse of `ground_point`.

    Solving `ground_point` for y gives
    `y = (h·cos(pitch) − X·sin(pitch)) / (X·cos(pitch) + h·sin(pitch))`,
    after which t and x follow directly.
    """
    den = forward * math.cos(pitch) + cam_h * math.sin(pitch)
    if abs(den) <= MIN_DENOMINATOR:
        return None
    y = (cam_h * math.cos(pitch) - forward * math.sin(pitch)) / den
    t_den = math.sin(pitch) + y * math.cos(pitch)
    if t_den <= MIN_DENOMINATOR:
        return None
    t = cam_h / t_den
    return cx + f * (-left / t), cy + f * y


def haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Great-circle distance in metres."""
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = p2 - p1, math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * EARTH_RADIUS_M * math.asin(min(1.0, math.sqrt(a)))


def interp_track(
    ts: list[float], lat: list[float], lon: list[float], t: float
) -> tuple[float, float]:
    """Position at time `t`, linearly interpolated between fixes.

    Clamps outside the track rather than extrapolating: a GPS fix that has not
    arrived yet is unknown, and inventing one by extending the last heading would
    place detections on road the vehicle may never have driven.
    """
    if not ts:
        raise ValueError("empty track")
    if t <= ts[0]:
        return lat[0], lon[0]
    if t >= ts[-1]:
        return lat[-1], lon[-1]

    hi = next(i for i, value in enumerate(ts) if value >= t)
    lo = hi - 1
    span = ts[hi] - ts[lo]
    w = 0.0 if span <= 0 else (t - ts[lo]) / span
    return lat[lo] + w * (lat[hi] - lat[lo]), lon[lo] + w * (lon[hi] - lon[lo])
