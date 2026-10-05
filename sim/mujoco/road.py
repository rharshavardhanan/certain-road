"""Seeded road layout and clustered damage, and its ground truth.

A road is a straight two-lane carriageway, x forward along the road from 0, y left from
the centre line. Damage is clustered, not scattered: parents are drawn along the road and
children fall around them (a Thomas process), linear cracks sit in the wheel paths, and
most potholes sit inside or beside an alligator patch, because that is where potholes
form. The same preset and seed always give the same `Road`, byte for byte as JSON.
"""

from __future__ import annotations

import json
import math
from dataclasses import asdict, dataclass, field
from pathlib import Path

import numpy as np
import yaml

from certain_road.core.paths import repo_root

CLASSES = ("linear_crack", "alligator_crack", "pothole")
CONFIG = repo_root() / "configs/sim/mujoco.yaml"


def _overlay(base: dict, over: dict) -> dict:
    out = dict(base)
    for k, v in over.items():
        out[k] = (
            _overlay(base[k], v) if isinstance(v, dict) and isinstance(base.get(k), dict) else v
        )
    return out


def load_config(look: str | None = None) -> dict:
    """The simulator config, with a look's overlay applied (`looks:` in the file).

    No look, or `v1`, is the base config: the simulator as committed at the `demo-v1` tag.
    A look changes only how the road is drawn and lit, never the road itself.
    """
    cfg = yaml.safe_load(CONFIG.read_text())
    if look is None:
        return cfg
    out = _overlay(cfg, cfg["looks"][look])
    out["look"] = look
    return out


@dataclass(frozen=True)
class Instance:
    id: int
    cls: str
    x_m: float  # centre along the road
    y_m: float  # centre, left of the centre line
    length_m: float  # ellipse major axis (full)
    width_m: float  # ellipse minor axis (full)
    angle_rad: float  # major axis from the road direction, anticlockwise
    area_m2: float  # true footprint: the ellipse
    texture: str
    bbox: tuple[float, float, float, float]  # x0, y0, x1, y1


@dataclass(frozen=True)
class Road:
    preset: str
    seed: int
    length_m: float
    lane_width_m: float
    drive_lane_y: float
    instances: tuple[Instance, ...] = field(default_factory=tuple)

    def to_json(self) -> str:
        return json.dumps(asdict(self), indent=1, sort_keys=True)

    @staticmethod
    def from_json(text: str) -> Road:
        d = json.loads(text)
        inst = tuple(Instance(**{**i, "bbox": tuple(i["bbox"])}) for i in d.pop("instances"))
        return Road(**d, instances=inst)

    def save(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(self.to_json())


def _bbox(x, y, length, width, angle):
    c, s = abs(math.cos(angle)), abs(math.sin(angle))
    hx = (length * c + width * s) / 2
    hy = (length * s + width * c) / 2
    return (round(x - hx, 4), round(y - hy, 4), round(x + hx, 4), round(y + hy, 4))


def _rates(preset: str, cfg: dict, rng, length: float) -> list[tuple[float, float, dict]]:
    """[(x0, x1, expected count per class)] over the road."""
    p = cfg["presets"][preset]
    if preset == "mixed":
        sw = length * rng.uniform(*p["switch_frac"])
        return [
            (0.0, sw, _counts(p["good"], sw, rng)),
            (sw, length, _counts(p["poor"], length - sw, rng)),
        ]
    if preset == "random":
        audit = json.loads((repo_root() / p["source"]).read_text())["splits"][p["split"]]
        n_img, n_bg = audit["images"], audit["backgrounds"]
        inst = audit["instances"]
        total = sum(inst.values())
        mean_damaged = total / (n_img - n_bg)
        mix = np.array([inst[c] for c in CLASSES], float) / total
        window = cfg["damage"]["window_m"]
        out = []
        for x0 in np.arange(0.0, length, window):
            if rng.random() < n_bg / n_img:
                continue
            n = 1 + rng.poisson(mean_damaged - 1)
            k = rng.multinomial(n, mix)
            out.append(
                (
                    float(x0),
                    float(min(x0 + window, length)),
                    dict(zip(CLASSES, map(float, k), strict=True), exact=True),
                )
            )
        return out
    return [(0.0, length, _counts(p, length, rng))]


def _counts(p: dict, span: float, rng) -> dict:
    out = {c: p.get(c, 0.0) * span / 100.0 for c in CLASSES}
    if "pothole_total" in p:
        out["pothole"] = float(rng.integers(p["pothole_total"][0], p["pothole_total"][1] + 1))
        out["exact_pothole"] = True
    return out


def generate(
    preset: str,
    seed: int,
    textures: dict[str, list[tuple[str, float, float]]],
    cfg: dict | None = None,
) -> Road:
    """`textures`: class -> [(name, crop aspect w/h, natural px per m or 0)]."""
    cfg = cfg or load_config()
    rc, dc = cfg["road"], cfg["damage"]
    rng = np.random.default_rng(seed)
    length = float(rng.uniform(*rc["length_m"]))
    lw = rc["lane_width_m"]
    lo_x, hi_x = rc["clean_start_m"], length - 2.0
    half = lw - 0.3  # stay off the kerb
    placed: list[Instance] = []

    def lateral(cls):
        lane = (
            rc["drive_lane_y"]
            if rng.random() < dc["lateral_in_drive_lane"]
            else -rc["drive_lane_y"]
        )
        if cls == "linear_crack":
            return lane + rng.choice([-1, 1]) * dc["wheelpath_offset_m"] + rng.normal(0, 0.15)
        return lane + rng.normal(0, 0.6)

    def size(cls, tex):
        name, aspect, natural = tex[:3]
        if natural:  # photographed scale, jittered
            s = rng.uniform(*dc["natural_scale"][cls])
            return name, aspect, natural / s  # px per m after jitter
        d = float(rng.uniform(*dc["pothole_diameter_m"]))
        return name, aspect, d

    def add(cls, x, y, angle=None):
        tex = textures[cls][rng.integers(len(textures[cls]))]
        name, aspect, v = size(cls, tex)
        if tex[2]:  # natural scale: v is px per m; crop size in m comes from the crop's px
            length_m, width_m = tex[3] / v, tex[4] / v
        else:
            length_m = v
            width_m = v / min(aspect, 1.6)
        if width_m > length_m:
            length_m, width_m = width_m, length_m
        if angle is None:
            if cls == "linear_crack":
                angle = (0.0 if rng.random() < 0.7 else math.pi / 2) + rng.normal(0, 0.12)
            else:
                angle = rng.uniform(0, math.pi)
        # clamp by the rotated footprint's half-height, so no patch spills under a kerb
        hy = (length_m * abs(math.sin(angle)) + width_m * abs(math.cos(angle))) / 2
        y = float(np.clip(y, -half + hy, half - hy))
        x = float(np.clip(x, lo_x, hi_x))
        area = math.pi / 4 * length_m * width_m
        bb = _bbox(x, y, length_m, width_m, angle)
        for o in placed:  # reject heavy overlap
            ix = max(0.0, min(bb[2], o.bbox[2]) - max(bb[0], o.bbox[0]))
            iy = max(0.0, min(bb[3], o.bbox[3]) - max(bb[1], o.bbox[1]))
            if ix * iy > dc["max_overlap"] * min(area, o.area_m2) and not (
                cls == "pothole" and o.cls == "alligator_crack"
            ):
                return None
        inst = Instance(
            len(placed),
            cls,
            round(x, 4),
            round(y, 4),
            round(length_m, 4),
            round(width_m, 4),
            round(angle % math.pi, 4),
            round(area, 5),
            name,
            bb,
        )
        placed.append(inst)
        return inst

    sx, sy = dc["cluster_sigma_m"]
    for x0, x1, counts in _rates(preset, cfg, rng, length):
        x0, x1 = max(x0, lo_x), min(x1, hi_x)
        if x1 <= x0:
            continue
        for cls in ("alligator_crack", "pothole", "linear_crack"):
            exact = counts.get("exact") or (cls == "pothole" and counts.get("exact_pothole"))
            n = int(round(counts[cls])) if exact else int(rng.poisson(counts[cls]))
            if n == 0:
                continue
            alligators = [i for i in placed if i.cls == "alligator_crack" and x0 <= i.x_m <= x1]
            n_par = max(1, int(round(n * cfg["clusters_per_instance"])))
            parents = [(rng.uniform(x0, x1), lateral(cls)) for _ in range(n_par)]
            for _ in range(n):
                if (
                    cls == "pothole"
                    and alligators
                    and rng.random() < dc["attach_pothole_to_alligator"]
                ):
                    a = alligators[rng.integers(len(alligators))]
                    add(
                        cls,
                        a.x_m + rng.normal(0, a.length_m / 3),
                        a.y_m + rng.normal(0, a.width_m / 3),
                    )
                    continue
                px, py = parents[rng.integers(n_par)]
                if cls == "linear_crack":
                    add(cls, px + rng.normal(0, sx * 2), py)
                else:
                    add(cls, px + rng.normal(0, sx), py + rng.normal(0, sy))
    # renumber in road order so ids read naturally
    ordered = sorted(placed, key=lambda i: (i.x_m, i.y_m))
    final = tuple(Instance(**{**asdict(i), "id": k, "bbox": i.bbox}) for k, i in enumerate(ordered))
    return Road(preset, seed, round(length, 3), lw, rc["drive_lane_y"], final)
