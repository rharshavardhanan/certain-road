"""Render the simulated robot's camera frame: what `project.py` projects, as pixels.

**Why this exists.** `project.py` turns a world-space pothole straight into a box; no
image ever exists in between. A ROS camera topic, and any detector run on it, need one
(D093). This renders it by running the same idealised projection backwards: every pixel
is mapped to the ground point that `project._image_v` and `project._image_u` would send
to that pixel, and coloured by what lies there.

**Consistency is the contract.** Because the mapping is the exact inverse, a rendered
pothole lands inside the box `project_pothole` reports for it, give or take a pixel at
the disc's tangents. A test pins that, so the image and the ground-truth boxes can never
drift apart.

**What it is not.** A road photograph. Flat grey asphalt with dark discs is far outside
the RDD2022 photos Model P and Model B were trained on, so a detector missing these
potholes says nothing about real roads. `sim/mujoco` is the photographic renderer (D087).
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

import numpy as np
import yaml

from certain_road.sim.model import Camera, RobotState
from certain_road.sim.scenario import Pothole

# Odd multipliers for a spatial hash, world cell -> pseudo-random asphalt shade, in
# wrapping uint32 arithmetic. Hash constants, not tunables: the texture's look is config.
_HASH_X = np.uint32(73856093)
_HASH_Y = np.uint32(19349663)
_HASH_MIX = np.uint32(2654435761)
_HASH_TOP_BYTE = 24  # keep the hash's best-mixed 8 bits
_BYTE_MAX = 255


@dataclass(frozen=True)
class Palette:
    sky_rgb: tuple[int, int, int]
    asphalt_rgb: tuple[int, int, int]
    asphalt_texture_m: float
    asphalt_noise: int
    pothole_rgb: tuple[int, int, int]
    pothole_rim_rgb: tuple[int, int, int]
    pothole_rim_frac: float


def load_palette(path: Path) -> Palette:
    raw = yaml.safe_load(Path(path).read_text())
    rgb = lambda key: tuple(int(c) for c in raw[key])  # noqa: E731
    return Palette(
        sky_rgb=rgb("sky_rgb"),
        asphalt_rgb=rgb("asphalt_rgb"),
        asphalt_texture_m=float(raw["asphalt_texture_m"]),
        asphalt_noise=int(raw["asphalt_noise"]),
        pothole_rgb=rgb("pothole_rgb"),
        pothole_rim_rgb=rgb("pothole_rim_rgb"),
        pothole_rim_frac=float(raw["pothole_rim_frac"]),
    )


@lru_cache(maxsize=4)
def ground_points(camera: Camera) -> tuple[int, np.ndarray, np.ndarray]:
    """`(horizon_row, forward_m, lateral_m)` for every pixel at or below the horizon.

    The inverse of `project._image_v` and `project._image_u`, at pixel centres. Rows
    above `horizon_row` see sky; the arrays cover rows `horizon_row:` only, which keeps
    the per-frame work to the ground the camera actually sees.
    """
    v = np.arange(camera.img_h, dtype=np.float64) + 0.5
    u = np.arange(camera.img_w, dtype=np.float64) + 0.5

    # _image_v: v = h/2 * (1 + tan(below - pitch) / tan(vfov/2))
    from_axis = np.arctan((v / (camera.img_h / 2.0) - 1.0) * np.tan(camera.vfov_rad / 2.0))
    below = from_axis + camera.pitch_rad
    horizon_row = int(np.argmax(below > 0.0)) if (below > 0.0).any() else camera.img_h
    forward_row = camera.height_m / np.tan(below[horizon_row:])

    # _image_u: u = w/2 * (1 - tan(atan2(lateral, forward)) / tan(hfov/2))
    tan_lateral = (1.0 - u / (camera.img_w / 2.0)) * np.tan(camera.hfov_rad / 2.0)

    forward = np.repeat(forward_row[:, None], camera.img_w, axis=1).astype(np.float32)
    lateral = (forward_row[:, None] * tan_lateral[None, :]).astype(np.float32)
    for a in (forward, lateral):
        a.flags.writeable = False  # cached and shared between calls
    return horizon_row, forward, lateral


def render_frame(
    state: RobotState,
    potholes: Iterable[Pothole],
    camera: Camera,
    palette: Palette,
) -> np.ndarray:
    """One RGB frame, shape (img_h, img_w, 3), uint8. Deterministic.

    The asphalt shade is hashed from world-fixed cells, so the texture stays put on the
    ground and flows past as the robot drives, which is what makes motion visible.
    """
    horizon, forward, lateral = ground_points(camera)
    cos_h, sin_h = np.float32(np.cos(state.heading)), np.float32(np.sin(state.heading))
    wx = np.float32(state.x) + forward * cos_h - lateral * sin_h
    wy = np.float32(state.y) + forward * sin_h + lateral * cos_h

    cell = np.float32(1.0 / palette.asphalt_texture_m)
    ix = np.floor(wx * cell).astype(np.int32).view(np.uint32)
    iy = np.floor(wy * cell).astype(np.int32).view(np.uint32)
    byte = (((ix * _HASH_X) ^ (iy * _HASH_Y)) * _HASH_MIX) >> _HASH_TOP_BYTE
    n = palette.asphalt_noise
    shade = byte.astype(np.int16) * (2 * n) // _BYTE_MAX - n

    img = np.empty((camera.img_h, camera.img_w, 3), dtype=np.uint8)
    img[:horizon] = palette.sky_rgb
    asphalt = np.asarray(palette.asphalt_rgb, dtype=np.int16)
    ground = img[horizon:]
    ground[:] = np.clip(asphalt + shade[..., None], 0, _BYTE_MAX)

    for p in potholes:
        d2 = (wx - np.float32(p.x)) ** 2 + (wy - np.float32(p.y)) ** 2
        ground[d2 <= np.float32(p.radius**2)] = palette.pothole_rim_rgb
        core = np.float32((p.radius * (1.0 - palette.pothole_rim_frac)) ** 2)
        ground[d2 <= core] = palette.pothole_rgb

    return img
