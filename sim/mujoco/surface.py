"""Bake the road surface into texture tiles: asphalt, markings, then damage.

Tiles cover the carriageway, x along the road and y across it. Row 0 is the right edge
(y = -width/2), which matches how MuJoCo maps a texture onto the road meshes (scene.py).
Everything random is seeded by position, not by tile, so tile borders are seamless: an
asphalt stamp or a damage patch that crosses a border is drawn identically on both sides.

Damage is alpha-composited onto the asphalt with a feathered, slightly irregular ellipse,
and each patch is colour-matched to the asphalt around it. This is what keeps a pasted
photo from reading as a rectangle.
"""

from __future__ import annotations

import math

import cv2
import numpy as np

from sim.mujoco import textures
from sim.mujoco.road import Road


def _smoothstep(t):
    t = np.clip(t, 0, 1)
    return t * t * (3 - 2 * t)


class Baker:
    def __init__(self, road: Road, cfg: dict):
        self.road, self.cfg, self.sc = road, cfg, cfg["surface"]
        self.ppm = self.sc["px_per_m"]
        self.width = 2 * road.lane_width_m
        self.h = int(round(self.width * self.ppm))
        self.tile_w = int(round(self.sc["tile_m"] * self.ppm))
        self.n_tiles = math.ceil(road.length_m / self.sc["tile_m"])
        self.specs = textures.by_name()
        self._asphalt = self._prepare_asphalt()
        rng = np.random.default_rng([road.seed, 7])
        self.lattice_m = 2.0
        self.lattice = rng.normal(
            0, 1, (int(self.width / self.lattice_m) + 3, int(road.length_m / self.lattice_m) + 3)
        )

    def _prepare_asphalt(self) -> list[np.ndarray]:
        lvl = self.sc["asphalt_level"]
        natural = textures.manifest()["natural_px_per_m"]["bd_n6"]
        out = []
        for p in textures.asphalt_paths():
            rgb = textures.flatten(textures._read(p), self.sc["flatten_sigma_frac"])
            s = self.ppm / natural
            rgb = cv2.resize(rgb, None, fx=s, fy=s, interpolation=cv2.INTER_AREA)
            m, sd = rgb.reshape(-1, 3).mean(0), rgb.reshape(-1, 3).std(0).mean()
            rgb = (rgb - m) * (lvl["std"] / 255 / sd) + np.array(lvl["mean"]) / 255
            out.append(np.clip(rgb, 0, 1).astype(np.float32))
        return out

    def _base(self, k: int) -> np.ndarray:
        """Asphalt for tile k: overlapping stamps with cosine weights, seeded by grid cell."""
        h, w = self.h, self.tile_w
        acc = np.zeros((h, w, 3), np.float32)
        wsum = np.zeros((h, w), np.float32)
        step = 96  # stamp pitch in px: well under every stamp so none leaves a gap
        x_off = k * w
        for gi in range((x_off - 400) // step, (x_off + w + 400) // step + 1):
            for gj in range(-3, h // step + 3):
                rng = np.random.default_rng([self.road.seed, 11, gi + 1000, gj + 1000])
                src = self._asphalt[rng.integers(len(self._asphalt))]
                src = np.rot90(src, rng.integers(4))
                if rng.random() < 0.5:
                    src = src[:, ::-1]
                sh, sw = src.shape[:2]
                x0 = gi * step + int(rng.integers(-step // 3, step // 3)) - x_off
                y0 = gj * step + int(rng.integers(-step // 3, step // 3))
                ax0, ay0 = max(x0, 0), max(y0, 0)
                ax1, ay1 = min(x0 + sw, w), min(y0 + sh, h)
                if ax1 <= ax0 or ay1 <= ay0:
                    continue
                wy = np.sin(np.linspace(0, np.pi, sh))[ay0 - y0 : ay1 - y0]
                wx = np.sin(np.linspace(0, np.pi, sw))[ax0 - x0 : ax1 - x0]
                wt = (wy[:, None] * wx[None, :]) ** 2 + 1e-4
                acc[ay0:ay1, ax0:ax1] += (
                    src[ay0 - y0 : ay1 - y0, ax0 - x0 : ax1 - x0] * wt[..., None]
                )
                wsum[ay0:ay1, ax0:ax1] += wt
        return acc / wsum[..., None]

    def _coords(self, k):
        x = k * self.sc["tile_m"] + (np.arange(self.tile_w) + 0.5) / self.ppm
        y = -self.width / 2 + (np.arange(self.h) + 0.5) / self.ppm
        return x, y

    def _shade(self, img, k):
        x, y = self._coords(k)
        mx = (x / self.lattice_m).astype(np.float32)
        my = ((y + self.width / 2) / self.lattice_m).astype(np.float32)
        gx, gy = np.meshgrid(mx, my)
        low = cv2.remap(self.lattice.astype(np.float32), gx, gy, cv2.INTER_CUBIC)
        f = 1 + self.sc["lowfreq_variation"] * low
        dl = self.road.drive_lane_y
        wp = sum(
            np.exp(-(((y - c) / 0.35) ** 2)) for c in (dl - 0.9, dl + 0.9, -dl - 0.9, -dl + 0.9)
        )
        f = f * (1 - self.sc["wheelpath_darkening"] * wp)[:, None]
        return img * f[..., None]

    def _markings(self, img, k):
        rc = self.cfg["road"]
        x, y = self._coords(k)
        mw = rc["marking_width_m"] / 2
        dash, gap = rc["centre_dash_m"]
        edge = self.width / 2 - rc["edge_line_inset_m"]
        on_x = (x % (dash + gap)) < dash
        centre = (np.abs(y) < mw)[:, None] & on_x[None, :]
        edges = (np.abs(np.abs(y) - edge) < mw)[:, None] & np.ones_like(on_x)[None, :]
        mask = (centre | edges).astype(np.float32)
        mask = cv2.GaussianBlur(mask, (0, 0), 0.8)
        rng = np.random.default_rng([self.road.seed, 13, k])
        wear = cv2.GaussianBlur(rng.random(mask.shape).astype(np.float32), (0, 0), 2.0)
        alpha = mask * np.clip(0.55 + 0.9 * (wear - 0.5) * 3 + 0.3, 0, 0.92)
        paint = np.array([0.9, 0.9, 0.87], np.float32)
        return img * (1 - alpha[..., None]) + paint * alpha[..., None]

    def _damage(self, img, k):
        x0m = k * self.sc["tile_m"]
        x1m = x0m + self.sc["tile_m"]
        for inst in self.road.instances:
            if inst.bbox[2] < x0m or inst.bbox[0] > x1m:
                continue
            self._stamp(img, k, inst)
        return img

    def _stamp(self, img, k, inst):
        sc = self.sc
        spec = self.specs[inst.texture]
        patch = textures.crop(spec, sc["flatten_sigma_frac"])
        if patch.shape[0] > patch.shape[1]:
            patch = np.rot90(patch).copy()
        # resample to twice the bake resolution before the warp
        tw = max(8, int(inst.length_m * self.ppm * 2))
        th = max(4, int(inst.width_m * self.ppm * 2))
        patch = cv2.resize(patch, (tw, th), interpolation=cv2.INTER_AREA)
        rng = np.random.default_rng([self.road.seed, 17, inst.id])
        uu, vv = np.meshgrid(np.linspace(-1, 1, tw), np.linspace(-1, 1, th))
        noise = cv2.resize(
            rng.random((6, 6)).astype(np.float32), (tw, th), interpolation=cv2.INTER_CUBIC
        )
        r = np.sqrt(uu**2 + vv**2) * (1 + sc["edge_noise"] * (noise - 0.5))
        alpha = _smoothstep((1 - r) / sc["feather"]).astype(np.float32)
        # tile px -> patch px
        a = inst.angle_rad
        ca, sa = math.cos(a), math.sin(a)
        su, sv = tw / inst.length_m, th / inst.width_m
        ox = k * sc["tile_m"] + 0.5 / self.ppm - inst.x_m
        oy = -self.width / 2 + 0.5 / self.ppm - inst.y_m
        d = 1 / self.ppm
        m = np.array(
            [
                [su * ca * d, su * sa * d, su * (ca * ox + sa * oy) + tw / 2],
                [-sv * sa * d, sv * ca * d, sv * (-sa * ox + ca * oy) + th / 2],
            ],
            np.float32,
        )
        x0 = int(max(0, (inst.bbox[0] - k * sc["tile_m"]) * self.ppm - 2))
        x1 = int(min(self.tile_w, (inst.bbox[2] - k * sc["tile_m"]) * self.ppm + 2))
        y0 = int(max(0, (inst.bbox[1] + self.width / 2) * self.ppm - 2))
        y1 = int(min(self.h, (inst.bbox[3] + self.width / 2) * self.ppm + 2))
        if x1 <= x0 or y1 <= y0:
            return
        msub = m.copy()
        msub[:, 2] += m[:, 0] * x0 + m[:, 1] * y0
        size = (x1 - x0, y1 - y0)
        flags = cv2.INTER_LINEAR | cv2.WARP_INVERSE_MAP
        wp = cv2.warpAffine(patch, msub, size, flags=flags, borderMode=cv2.BORDER_REFLECT)
        wa = cv2.warpAffine(
            alpha, msub, size, flags=flags, borderMode=cv2.BORDER_CONSTANT, borderValue=0
        )
        base = img[y0:y1, x0:x1]
        ring = (wa > 0.05) & (wa < 0.5)
        inside = wa > 0.05
        if ring.sum() > 20 and inside.sum() > 20:
            # match the clean surface between cracks, not the mean: cracks must keep
            # the patch darker on average, or minification at a grazing view erases it
            mp, sp = (
                np.percentile(wp[ring], sc["colour_match_percentile"], axis=0),
                wp[ring].std(0) + 1e-3,
            )
            mb, sb = base[inside].mean(0), base[inside].std(0) + 1e-3
            # shift toward the asphalt's mean; keep the damage's own contrast
            wp = (
                (wp - mp) * (sb / sp) ** sc["colour_match_std"]
                + mp
                + sc["colour_match_mean"] * (mb - mp)
            )
        if inst.cls == "pothole":
            # standing water is smooth; seen at a grazing angle it mirrors the bright sky
            lum = wp.mean(axis=2)
            mu = cv2.GaussianBlur(lum, (0, 0), 2.0)
            sd = np.sqrt(np.maximum(cv2.GaussianBlur(lum * lum, (0, 0), 2.0) - mu * mu, 0))
            water = cv2.GaussianBlur(
                (sd < sc["water_smoothness"]).astype(np.float32), (0, 0), 1.5
            ) * (wa > 0.6)
            sky = np.array(self.cfg["scene"]["sky"]["horizon"], np.float32)
            wp = wp * (1 - sc["water_sheen"] * water[..., None]) + sky * (
                sc["water_sheen"] * water[..., None]
            )
            wp = (
                wp
                * (1 - sc["pothole_depth_shade"] * _smoothstep((wa - 0.5) / 0.5) * (1 - water))[
                    ..., None
                ]
            )
            # the sun-side wall shadows the floor: alpha minus itself moved downstream
            d = np.array(self.cfg["scene"]["sun_dir"][:2], float)
            d = d / (np.linalg.norm(d) + 1e-9) * 0.06 * self.ppm
            moved = cv2.warpAffine(
                wa, np.float32([[1, 0, d[0]], [0, 1, d[1]]]), (wa.shape[1], wa.shape[0])
            )
            wall = np.clip(wa - moved, 0, 1) * (wa > 0.5)
            wp = wp * (1 - sc["pothole_wall_shade"] * wall)[..., None]
        else:
            lum = wp.mean(axis=2, keepdims=True)
            local = cv2.GaussianBlur(lum, (0, 0), 3.0)[..., None]
            wp = wp + (sc["crack_contrast"][inst.cls] - 1) * np.minimum(
                lum - local, 0
            )  # darken only dark lines
            if inst.cls in sc["widen_lines"]:
                wp = 0.5 * wp + 0.5 * cv2.erode(wp, np.ones((3, 3), np.uint8))
        img[y0:y1, x0:x1] = base * (1 - wa[..., None]) + np.clip(wp, 0, 1) * wa[..., None]

    def tile(self, k: int) -> np.ndarray:
        img = self._base(k)
        img = self._shade(img, k)
        img = self._damage(img, k)
        img = self._markings(img, k)
        return (np.clip(img, 0, 1) * 255).astype(np.uint8)
