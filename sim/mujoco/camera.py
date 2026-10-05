"""Render what the dashcam would record, not what the renderer draws.

A clean render is the biggest giveaway, so every frame goes through what a real camera
adds: pitch and roll from road roughness (smooth noise in distance, seeded), motion blur
from averaging sub-frames over the exposure, contrast, vignetting, sensor noise, and a
JPEG round-trip before the detector ever sees it.
"""

from __future__ import annotations

import math

import cv2
import mujoco
import numpy as np

from sim.mujoco.scene import camera_quat

NOISE_PAD = 64  # px of slack around the noise bank, for the random offset


class Camera:
    def __init__(self, model: mujoco.MjModel, cam: dict, cfg: dict, seed: int, drive_y: float):
        self.m, self.cam, self.fx = model, cam, cfg["camera_effects"]
        self.d = mujoco.MjData(model)
        self.ss = cfg["camera_effects"]["supersample"]
        self.r = mujoco.Renderer(model, cam["h"] * self.ss, cam["w"] * self.ss)
        self.cid = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_CAMERA, "cam")
        self.y = drive_y
        rng = np.random.default_rng([seed, 31])
        self.knots = rng.normal(0, 1, (2, 4096))
        h, w = cam["h"], cam["w"]
        yy, xx = np.mgrid[0:h, 0:w]
        rr = ((xx - w / 2) ** 2 + (yy - h / 2) ** 2) / ((w / 2) ** 2 + (h / 2) ** 2)
        self.vig = (1 - self.fx["vignette"] * rr)[..., None].astype(np.float32)
        self.rng = np.random.default_rng([seed, 37])
        # sensor noise: one seeded bank, sliced at a random offset per frame, because
        # drawing 2.7 M normals every frame cost 14 ms of a 33 ms budget
        pad = NOISE_PAD
        self.noise = self.rng.normal(0, self.fx["sensor_noise"], (h + pad, w + pad, 3)).astype(
            np.float32
        )
        lut = (np.arange(256) / 255.0 - 0.5) * self.fx["contrast"] + 0.5
        self.lut = (np.clip(lut, 0, 1) * 255).round().astype(np.uint8)

    def _noise(self, row, x):
        t = x / self.fx["noise_corr_m"]
        i = int(math.floor(t)) % (self.knots.shape[1] - 1)
        f = t - math.floor(t)
        f = f * f * (3 - 2 * f)
        return self.knots[row, i] * (1 - f) + self.knots[row, i + 1] * f

    def _raw(self, x: float) -> np.ndarray:
        fx = self.fx
        pitch = self.cam["pitch"] + math.radians(fx["pitch_noise_deg"]) * self._noise(0, x)
        roll = math.radians(fx["roll_noise_deg"]) * self._noise(1, x)
        self.m.cam_quat[self.cid] = camera_quat(pitch, roll)
        self.d.mocap_pos[0] = [x, self.y, 0]
        mujoco.mj_forward(self.m, self.d)
        self.r.update_scene(self.d, camera=self.cid)
        self.r.scene.flags[mujoco.mjtRndFlag.mjRND_FOG] = True
        big = self.r.render()
        return cv2.resize(big, (self.cam["w"], self.cam["h"]), interpolation=cv2.INTER_AREA)

    def frame(self, x: float) -> np.ndarray:
        """BGR uint8 at distance x along the road, as the detector receives it.

        BGR because ultralytics reads a numpy image as BGR, as OpenCV does.
        """
        fx = self.fx
        n = fx["blur_subframes"]
        travel = self.cam["speed_mps"] * fx["exposure_s"]
        if n == 1:
            img = self._raw(x)
        else:
            acc = np.zeros((self.cam["h"], self.cam["w"], 3), np.float32)
            for k in range(n):
                acc += self._raw(x + travel * (k / (n - 1) - 0.5))
            img = (acc / n).round().astype(np.uint8)
        img = cv2.LUT(img, self.lut).astype(np.float32)
        img *= self.vig
        oy, ox = (int(v) for v in self.rng.integers(0, NOISE_PAD, 2))
        img += self.noise[oy : oy + img.shape[0], ox : ox + img.shape[1]]
        np.clip(img, 0, 255, out=img)
        bgr = cv2.cvtColor(img.astype(np.uint8), cv2.COLOR_RGB2BGR)
        ok, enc = cv2.imencode(".jpg", bgr, [cv2.IMWRITE_JPEG_QUALITY, fx["jpeg_quality"]])
        return cv2.imdecode(enc, cv2.IMREAD_COLOR)
