"""Look v2's 3D potholes: the road mesh sinks wherever the texture shows a pothole.

Each road tile becomes a grid mesh in place of a flat quad. The grid is coarse on flat road
and fine (`relief.fine_m`) across every pothole. A vertex inside a pothole drops by that
pothole's depth, shaped by the same feathered, irregular ellipse the surface baker paints
(`surface.stamp_alpha`). The hole therefore sits exactly under its texture, with walls the
scene's sun lights on one side and shadows on the other.

Depth is drawn per pothole from `relief.depth_m`, seeded by the road seed and the instance
id. It does not touch the road generator's random stream, so the ground truth is the same
in every look. The rim stays at road level, so the projected ground-truth boxes are unchanged.
"""

from __future__ import annotations

import math

import cv2
import mujoco
import numpy as np

from sim.mujoco.road import Road
from sim.mujoco.surface import _smoothstep, stamp_alpha


def _potholes(road: Road, x0: float, x1: float) -> list:
    return [i for i in road.instances if i.cls == "pothole" and i.bbox[2] > x0 and i.bbox[0] < x1]


def _sample(img: np.ndarray, col: np.ndarray, row: np.ndarray, border: int) -> np.ndarray:
    """Bilinear samples of img at (col, row), as the baker's warp samples it.

    cv2.remap takes maps under 32767 on a side, so the points are folded into rows of 4096.
    """
    n, w = col.size, 4096
    pad = -n % w
    c = np.pad(col.astype(np.float32).ravel(), (0, pad)).reshape(-1, w)
    r = np.pad(row.astype(np.float32).ravel(), (0, pad)).reshape(-1, w)
    out = cv2.remap(img, c, r, cv2.INTER_LINEAR, borderMode=border, borderValue=0)
    return out.ravel()[:n]


def depth_at(road: Road, cfg: dict, x: np.ndarray, y: np.ndarray) -> np.ndarray:
    """Depth below the road surface (metres, >= 0) at world points (x, y)."""
    rc, sc = cfg["relief"], cfg["surface"]
    x, y = np.asarray(x, np.float64), np.asarray(y, np.float64)
    depth = np.zeros(np.broadcast(x, y).shape)
    lo, hi = rc["wall_alpha"]
    for inst in _potholes(road, float(np.min(x)), float(np.max(x)) + 1e-9):
        alpha, tw, th = stamp_alpha(road.seed, inst, sc)
        ca, sa = math.cos(inst.angle_rad), math.sin(inst.angle_rad)
        dx, dy = x - inst.x_m, y - inst.y_m
        # the baker's tile-px -> patch-px map, applied to world points
        col = tw / inst.length_m * (ca * dx + sa * dy) + tw / 2
        row = th / inst.width_m * (-sa * dx + ca * dy) + th / 2
        inside = (col >= 0) & (col <= tw - 1) & (row >= 0) & (row <= th - 1)
        if not inside.any():
            continue
        a = _sample(alpha, col, row, cv2.BORDER_CONSTANT).reshape(depth.shape)
        rng = np.random.default_rng([road.seed, 31, inst.id])
        d = rng.uniform(*rc["depth_m"])
        floor = cv2.resize(
            rng.random((5, 5)).astype(np.float32), (tw, th), interpolation=cv2.INTER_CUBIC
        )
        rough = _sample(floor, col, row, cv2.BORDER_REPLICATE).reshape(depth.shape)
        here = d * _smoothstep((a - lo) / (hi - lo)) * (1 + rc["floor_roughness"] * (rough - 0.5))
        depth = np.maximum(depth, np.where(inside, here, 0.0))
    return depth


def _lines(lo: float, hi: float, coarse: float, bands: list[tuple[float, float]], fine: float):
    xs = [np.linspace(lo, hi, max(2, math.ceil((hi - lo) / coarse) + 1))]
    for a, b in bands:
        a, b = max(lo, a), min(hi, b)
        if b > a:
            xs.append(np.arange(a, b, fine))
    return np.unique(np.round(np.concatenate(xs), 5))


def tile_mesh(spec, name: str, road: Road, cfg: dict, x0: float, x1: float, w2: float) -> str:
    """A road tile as a grid mesh, sunk under its potholes, with the flat quad's UVs."""
    rc = cfg["relief"]
    pots = _potholes(road, x0, x1)
    m = rc["margin_m"]
    xs = _lines(
        x0, x1, rc["coarse_m"], [(p.bbox[0] - m, p.bbox[2] + m) for p in pots], rc["fine_m"]
    )
    ys = _lines(
        -w2, w2, rc["coarse_m"], [(p.bbox[1] - m, p.bbox[3] + m) for p in pots], rc["fine_m"]
    )
    gx, gy = np.meshgrid(xs, ys)  # rows along y, columns along x
    gz = -depth_at(road, cfg, gx, gy) if pots else np.zeros_like(gx)
    ny, nx = gx.shape
    idx = np.arange(nx * ny).reshape(ny, nx)
    a, b = idx[:-1, :-1].ravel(), idx[:-1, 1:].ravel()
    c, d = idx[1:, 1:].ravel(), idx[1:, :-1].ravel()
    faces = np.stack([a, b, c, a, c, d], 1).reshape(-1, 3)  # counter-clockwise from above
    mesh = spec.add_mesh(name=name)
    mesh.uservert = np.stack([gx, gy, gz], -1).ravel().tolist()
    mesh.userface = faces.ravel().tolist()
    uv = np.stack([(gx - x0) / (x1 - x0), (gy + w2) / (2 * w2)], -1)
    mesh.usertexcoord = uv.ravel().tolist()
    mesh.inertia = mujoco.mjtMeshInertia.mjMESH_INERTIA_SHELL
    return name
