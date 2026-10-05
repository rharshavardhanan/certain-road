"""The live screen: four panels and a caption bar, legible from 3 m on a projector.

- **Top left: camera.** The frame the models saw, with class-coloured boxes, confirmed tracks
  in green, the 12 m gate, and D006's survey ROI, which lights up at each 5 m sample.
- **Top right: survey map.** The road in plan with confirmed damage placed by the IPM, and
  each 50 m segment coloured by its vision-estimated PCI band as it completes.
- **Bottom left: counters.** Distance, segments scored, confirmed tracks per class, and the
  segment in progress.
- **Bottom right: drift.** D078's CUSUM log-wealth for Model B against its india_val
  reference, with the alarm threshold.

The screen only displays. Every number on it comes from the drive loop, the survey (real
certain_road.survey code) or the drift monitor (real certain_road.assess.drift code).
"""

from __future__ import annotations

import contextlib
import math
from functools import lru_cache

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont

from certain_road.core.geometry import ground_point, project
from certain_road.survey.scoring import BANDS
from sim.mujoco.road import CLASSES, Road
from sim.mujoco.survey import ipm_kw, roi, survey_camera

NAMES = {
    "pothole": "Potholes",
    "linear_crack": "Linear cracks",
    "alligator_crack": "Alligator cracks",
}
SOURCE = {"pothole": "Model P", "linear_crack": "Model B", "alligator_crack": "Model B"}


@lru_cache(maxsize=64)
def _font(path: str, px: int, weight: str) -> ImageFont.FreeTypeFont:
    try:
        f = ImageFont.truetype(path, px)
    except OSError:
        return ImageFont.load_default(px)
    with contextlib.suppress(OSError, ValueError):  # not a variable font: its one weight
        f.set_variation_by_name(weight.encode())
    return f


@lru_cache(maxsize=8192)
def _sprite(path: str, px: int, weight: str, s: str) -> tuple[np.ndarray, int, int]:
    f = _font(path, px, weight)
    left, top, right, bottom = f.getbbox(s)
    im = Image.new("L", (max(1, right - left), max(1, bottom - top)))
    ImageDraw.Draw(im).text((-left, -top), s, font=f, fill=255)
    return np.asarray(im, np.float32)[..., None] / 255.0, left, top


def blend(img: np.ndarray, x0: int, y0: int, alpha: np.ndarray, rgb) -> None:
    """Alpha-blend a single colour through `alpha` (h, w, 1) into img at (x0, y0), clipped."""
    h, w = alpha.shape[:2]
    xa, ya, xb, yb = max(0, x0), max(0, y0), min(img.shape[1], x0 + w), min(img.shape[0], y0 + h)
    if xa >= xb or ya >= yb:
        return
    a = alpha[ya - y0 : yb - y0, xa - x0 : xb - x0]
    r = img[ya:yb, xa:xb].astype(np.float32)
    img[ya:yb, xa:xb] = (r + (np.asarray(rgb, np.float32) - r) * a).astype(np.uint8)


class Ink:
    """Text in the screen's two faces. Positions are the top of the line, as in CSS."""

    def __init__(self, sc: dict):
        self.fonts, self.px = sc["fonts"], sc["px"]

    def _key(self, size, mono, weight):
        px = self.px[size] if isinstance(size, str) else size
        return self.fonts["mono" if mono else "sans"], px, weight

    def width(self, s: str, size="body", weight="Regular", mono=False) -> float:
        return _font(*self._key(size, mono, weight)).getlength(s)

    def put(self, img, x, y, s, rgb, size="body", weight="Regular", mono=False, align="left"):
        key = self._key(size, mono, weight)
        if align != "left":
            w = _font(*key).getlength(s)
            x -= w if align == "right" else w / 2
        a, left, top = _sprite(*key, s)
        blend(img, round(x + left), round(y + top), a, rgb)
        return x + _font(*key).getlength(s)


def chip(img, ink, x, y, s, fill, text_rgb, size="chip", weight="Semibold", pad=14, h=46):
    """A filled, rounded label. Returns its right edge."""
    w = int(ink.width(s, size, weight) + 2 * pad)
    r = h // 2 - 6
    cv2.rectangle(img, (x + r, y), (x + w - r, y + h), fill, -1, cv2.LINE_AA)
    cv2.rectangle(img, (x, y + r), (x + w, y + h - r), fill, -1, cv2.LINE_AA)
    for cx, cy in ((x + r, y + r), (x + w - r, y + r), (x + r, y + h - r), (x + w - r, y + h - r)):
        cv2.circle(img, (cx, cy), r, fill, -1, cv2.LINE_AA)
    px = ink.px[size]
    ink.put(img, x + pad, y + (h - px * 1.2) / 2, s, text_rgb, size, weight)
    return x + w


def honesty(road: Road, cfg: dict) -> str:
    """The line every render carries: what is simulated, what is real, and the texture credits."""
    return (
        f"Simulated {road.preset} road, seed {road.seed} · real Model P and Model B · "
        f"real certain_road.survey scoring and allocation · {cfg['credits']}"
    )


class Screen:
    def __init__(self, road: Road, cfg: dict, cam: dict, samples_total: int, per_segment: int):
        self.road, self.cfg, self.cam = road, cfg, cam
        sc = self.sc = cfg["screen"]
        self.rgb = {k: tuple(v) for k, v in sc["rgb"].items()}
        self.band_rgb = {k: tuple(v) for k, v in sc["band_rgb"].items()}
        self.cls_rgb = {k: tuple(v[::-1]) for k, v in cfg["drive"]["colours_bgr"].items()}
        self.ink = Ink(sc)
        self.W, self.H = sc["size"]
        g, ch = sc["gutter"], sc["caption_h"]
        half, top = self.W // 2, round(self.W / 2 * cam["h"] / cam["w"])
        self.cam_box = (0, 0, half, top)
        self.map_box = (half + g, 0, self.W - half - g, top)
        low = self.H - ch - top - g
        self.count_box = (0, top + g, half, low - g)
        self.drift_box = (half + g, top + g, self.W - half - g, low - g)
        self.cap_box = (0, self.H - ch, self.W, ch)
        self.camera = survey_camera(cam)
        self.per_segment = per_segment
        self.segments_total = math.ceil(samples_total / per_segment)
        self.tracks = {c: set() for c in CLASSES}
        self.dots: list[tuple[float, float, str]] = []
        self.trace: list[tuple[float, float]] = []
        self.alarm_m: float | None = None
        self.last_sample = -(10**9)
        self.caption = (
            f"Surveying a {road.preset} road, seed {road.seed}: "
            f"{road.length_m:.0f} m, two lanes, {cam['speed_mps'] * 3.6:.0f} km/h",
            None,
        )
        self.base = self._base()

    # ---- static layer -------------------------------------------------------------------
    def _panel(self, img, box):
        x, y, w, h = box
        img[y : y + h, x : x + w] = self.rgb["panel"]

    def _title(self, img, box, title, sub):
        x, y = box[0] + 32, box[1] + 24
        end = self.ink.put(img, x, y, title, self.rgb["text"], "title", "Semibold")
        self.ink.put(img, end + 16, y + 6, sub, self.rgb["muted"], "label")

    def _base(self) -> np.ndarray:
        img = np.empty((self.H, self.W, 3), np.uint8)
        img[:] = self.rgb["bg"]
        for b in (self.map_box, self.count_box, self.drift_box):
            self._panel(img, b)
        x, y, w, h = self.cap_box
        img[y : y + h, x : x + w] = self.rgb["panel"]
        self._title(img, self.map_box, "Survey map", "50 m segments by vision-estimated PCI band")
        self._title(img, self.count_box, "Survey", "confirmed = same track in 3 of 5 frames")
        self._title(img, self.drift_box, "Drift monitor", "Model B confidence vs india_val, CUSUM")
        ink, m = self.ink, self.rgb["muted"]
        ink.put(img, x + 40, y + 64, honesty(self.road, self.cfg), m, "small")
        # map: road plan, the segment row and the band legend
        mx, my, mw, _ = self.map_box
        self.sx = (mw - 80) / self.road.length_m
        self.mx0 = mx + 40
        lw = self.road.lane_width_m
        self.plan_mid, sy = my + 190, self.sc["map_lateral_px_per_m"]
        top, bot = self.plan_mid - lw * sy, self.plan_mid + lw * sy
        ink.put(img, self.mx0, my + 84, "Plan, to scale along the road", m, "label")
        cv2.rectangle(
            img, (self.mx0, int(top)), (self.mx0 + mw - 80, int(bot)), self.rgb["road"], -1
        )
        for xm in np.arange(0, self.road.length_m, 6.0):
            a = int(self.mx0 + xm * self.sx)
            cv2.line(
                img, (a, self.plan_mid), (int(a + 3 * self.sx), self.plan_mid), self.rgb["muted"], 1
            )
        ink.put(img, self.mx0, my + 296, "Vision-estimated PCI by segment", m, "label")
        self.seg_y0, self.seg_y1 = my + 330, my + 430
        cv2.rectangle(
            img, (self.mx0, self.seg_y0), (self.mx0 + mw - 80, self.seg_y1), self.rgb["line"], 1
        )
        lx = self.mx0
        for _, _, name in BANDS:
            cv2.rectangle(img, (lx, my + 466), (lx + 18, my + 484), self.band_rgb[name], -1)
            lx = int(ink.put(img, lx + 26, my + 463, name, m, "small") + 22)
        return img

    # ---- per frame ----------------------------------------------------------------------
    def update(self, rec, bgr: np.ndarray, drv) -> np.ndarray:
        """Absorb one frame record and return the screen as BGR."""
        for d in rec.dets:
            if d.confirmed and d.track not in self.tracks[d.cls]:
                self.tracks[d.cls].add(d.track)
                g = ground_point((d.x1 + d.x2) / 2, d.y2, **ipm_kw(self.camera))
                if g is not None:
                    self.dots.append((rec.x_m + g[0], self.road.drive_lane_y + g[1], d.cls))
        if rec.sampled:
            self.last_sample = rec.frame
        if rec.drift is not None:
            self.trace.append((rec.x_m, rec.drift["log_m"]))
            if rec.drift["alarmed"] and self.alarm_m is None:
                self.alarm_m = rec.x_m
                self.caption = (
                    f"Drift alarm at {rec.x_m:.0f} m: Model B's confidence has left "
                    "its india_val reference",
                    "alarm",
                )
        if rec.closed is not None:
            self.caption = self._segment_caption(rec.closed, drv.survey.segments)
        img = self.base.copy()
        self._camera(img, rec, bgr, drv)
        self._map(img, rec, drv)
        self._counts(img, rec, drv)
        self._drift(img, drv)
        self._caption(img)
        return cv2.cvtColor(img, cv2.COLOR_RGB2BGR)

    def _segment_caption(self, s, segments) -> tuple[str, str]:
        text = f"Segment {s.index + 1} complete: vision-estimated PCI {s.vision_estimated_pci:.0f}"
        names = [b[2] for b in BANDS][::-1]  # Failed .. Good
        if len(segments) > 1:
            prev = segments[-2].band
            if names.index(prev) - names.index(s.band) >= self.cfg["survey"]["band_drop_caption"]:
                text += f", down from {prev}"
        return text, s.band

    def _camera(self, img, rec, bgr, drv):
        x, y, w, h = self.cam_box
        k = w / bgr.shape[1]
        view = cv2.resize(
            cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB), (w, h), interpolation=cv2.INTER_AREA
        )
        near, far, half = roi(self.cfg)
        quad = (
            np.array(
                [
                    project(f, s * half, **ipm_kw(self.camera))
                    for f, s in ((near, 1), (far, 1), (far, -1), (near, -1))
                ]
            )
            * k
        )
        flash = 1 - (rec.frame - self.last_sample) / self.sc["roi_flash_frames"]
        if flash > 0:
            over = view.copy()
            cv2.fillPoly(over, [quad.astype(np.int32)], (255, 255, 255), cv2.LINE_AA)
            view = cv2.addWeighted(over, 0.28 * flash, view, 1 - 0.28 * flash, 0)
        cv2.polylines(view, [quad.astype(np.int32)], True, (235, 235, 235), 1, cv2.LINE_AA)
        gy = int(drv.horizon * k)
        for gx in range(0, w, 24):
            cv2.line(view, (gx, gy), (gx + 12, gy), (210, 210, 210), 1, cv2.LINE_AA)
        for d in sorted(rec.dets, key=lambda d: d.confirmed):
            c = self.cls_rgb["confirmed"] if d.confirmed else self.cls_rgb[d.cls]
            p1, p2 = (int(d.x1 * k), int(d.y1 * k)), (int(d.x2 * k), int(d.y2 * k))
            cv2.rectangle(view, p1, p2, c, 3 if d.confirmed else 2, cv2.LINE_AA)
        img[y : y + h, x : x + w] = view
        strip = np.zeros((44, w, 1), np.float32) + 0.8
        blend(img, x, y, strip, self.rgb["dark"])
        ink = self.ink
        end = ink.put(img, x + 20, y + 9, "Camera", self.rgb["text"], "label", "Semibold")
        ink.put(
            img,
            end + 12,
            y + 9,
            "1280×720 · 1.3 m high · 10° down",
            self.rgb["muted"],
            "label",
        )
        short = {"pothole": "Pothole", "linear_crack": "Linear", "alligator_crack": "Alligator"}
        legend = [(short[c], self.cls_rgb[c]) for c in short] + [
            ("Confirmed", self.cls_rgb["confirmed"])
        ]
        lx = x + w - 20  # in the top strip, right-aligned, clear of the road
        for name, rgb in reversed(legend):
            ink.put(img, lx, y + 9, name, rgb, "label", "Semibold", align="right")
            lx -= ink.width(name, "label", "Semibold") + 18
        if rec.sampled or flash > 0:
            white, dark = (255, 255, 255), self.rgb["dark"]
            chip(img, ink, x + 16, y + h - 56, "5 m survey sample", dark, white, "label", h=40)

    def _map(self, img, rec, drv):
        sy = self.sc["map_lateral_px_per_m"]
        for xm, ym, cls in self.dots:
            cv2.circle(
                img,
                (int(self.mx0 + xm * self.sx), int(self.plan_mid - ym * sy)),
                5,
                self.cls_rgb[cls],
                -1,
                cv2.LINE_AA,
            )
        vx = int(self.mx0 + rec.x_m * self.sx)
        vy = int(self.plan_mid - self.road.drive_lane_y * sy)
        cv2.fillPoly(
            img,
            [np.array([(vx + 12, vy), (vx - 6, vy - 10), (vx - 6, vy + 10)])],
            self.rgb["text"],
            cv2.LINE_AA,
        )
        for s in drv.survey.segments:
            a, b = int(self.mx0 + s.x0_m * self.sx), int(self.mx0 + s.x1_m * self.sx)
            fill = self.band_rgb[s.band]
            cv2.rectangle(img, (a + 1, self.seg_y0), (b - 1, self.seg_y1), fill, -1)
            txt = f"{s.vision_estimated_pci:.0f}"
            if self.ink.width(txt, "title", "Semibold") < b - a - 8:
                tc = self.rgb["dark"] if s.band in self.sc["dark_text_bands"] else (255, 255, 255)
                self.ink.put(
                    img, (a + b) / 2, self.seg_y0 + 34, txt, tc, "title", "Semibold", align="center"
                )
        run = drv.survey.running()
        if run is not None:
            near, _, _ = roi(self.cfg)
            a = int(self.mx0 + (drv.survey.samples[-run["n_samples"]]["x_m"] + near) * self.sx)
            b = int(self.mx0 + (rec.x_m + near) * self.sx)
            cv2.rectangle(
                img, (a + 1, self.seg_y0), (max(a + 2, b), self.seg_y1), self.rgb["line"], -1
            )

    def _counts(self, img, rec, drv):
        x, y, w, h = self.count_box
        ink, t, m = self.ink, self.rgb["text"], self.rgb["muted"]
        c0 = x + 32
        ink.put(img, c0, y + 84, "Distance", m, "label")
        vx = c0 + ink.width("0000", "value", "Medium")  # values right-align here; units stay put
        ink.put(img, vx, y + 112, f"{rec.x_m:.0f}", t, "value", "Medium", align="right")
        ink.put(img, vx + 12, y + 140, f"m of {self.road.length_m:.0f}", m, "label")
        done = len(drv.survey.segments)
        ink.put(img, c0, y + 200, "Segments scored", m, "label")
        ink.put(img, vx, y + 228, str(done), t, "value", "Medium", align="right")
        ink.put(img, vx + 12, y + 256, f"of {self.segments_total}", m, "label")
        c1, right = x + w // 2 + 16, x + w - 40
        ink.put(img, c1, y + 84, "Confirmed tracks", m, "label")
        for i, cls in enumerate(("pothole", "alligator_crack", "linear_crack")):
            ry = y + 122 + i * 64
            cv2.circle(img, (c1 + 9, ry + 18), 9, self.cls_rgb[cls], -1, cv2.LINE_AA)
            end = ink.put(img, c1 + 30, ry, NAMES[cls], t, "body")
            ink.put(img, end + 10, ry + 6, SOURCE[cls], m, "small")
            ink.put(
                img, right, ry - 8, str(len(self.tracks[cls])), t, "count", "Medium", align="right"
            )
        run = drv.survey.running()
        cv2.line(img, (c0, y + h - 112), (x + w - 40, y + h - 112), self.rgb["line"], 1)
        if run is None:
            ink.put(img, c0, y + h - 86, "Next segment starts at the next 5 m sample", m, "label")
            return
        k, n = run["n_samples"], self.per_segment
        label = f"Segment {run['index'] + 1} in progress · {k} of {n} samples · so far"
        ink.put(img, c0, y + h - 92, label, m, "label")
        band = run["band"]
        tc = self.rgb["dark"] if band in self.sc["dark_text_bands"] else (255, 255, 255)
        chip(img, ink, c0, y + h - 58, f"{run['pci']:.0f}  {band}", self.band_rgb[band], tc)

    def _drift(self, img, drv):
        x, y, w, h = self.drift_box
        ink, m = self.ink, self.rgb["muted"]
        p0, p1, q0, q1 = x + 96, x + w - 48, y + 120, y + h - 64
        thr = drv.drift.log_threshold
        top = max(thr * 1.4, max((v for _, v in self.trace), default=0) * 1.08)

        def pt(xm, v):
            return int(p0 + xm / self.road.length_m * (p1 - p0)), int(q1 - v / top * (q1 - q0))

        cv2.line(img, (p0, q1), (p1, q1), self.rgb["line"], 1)
        tick = self.sc["drift_x_tick_m"]
        for xm in range(0, int(self.road.length_m) + 1, tick):
            px, _ = pt(xm, 0)
            cv2.line(img, (px, q1), (px, q1 + 6), self.rgb["line"], 1)
            ink.put(img, px, q1 + 12, f"{xm} m" if xm == 0 else f"{xm}", m, "small", align="center")
        ink.put(img, p0 - 12, q1 - 12, "0", m, "small", align="right")
        _, ty = pt(0, thr)
        for gx in range(p0, p1, 18):
            cv2.line(img, (gx, ty), (min(gx + 10, p1), ty), self.rgb["alarm"], 2, cv2.LINE_AA)
        ink.put(
            img,
            p1,
            ty - 30,
            "alarm threshold, wealth 10⁴",
            self.rgb["alarm"],
            "small",
            align="right",
        )
        ink.put(img, p0, q0 - 34, "CUSUM log-wealth, one point per 5 m sample", m, "small")
        if len(self.trace) > 1:
            pts = [pt(a, v) for a, v in self.trace]
            cut = next(
                (
                    i
                    for i, (a, _) in enumerate(self.trace)
                    if self.alarm_m is not None and a >= self.alarm_m
                ),
                len(pts),
            )
            if cut > 0:
                cv2.polylines(
                    img,
                    [np.array(pts[: cut + 1], np.int32)],
                    False,
                    self.rgb["text"],
                    3,
                    cv2.LINE_AA,
                )
            if cut < len(pts):
                cv2.polylines(
                    img, [np.array(pts[cut:], np.int32)], False, self.rgb["alarm"], 3, cv2.LINE_AA
                )
        cx = x + w - 48
        if self.alarm_m is None:
            s = "No alarm"
            cx -= int(ink.width(s, "label", "Semibold") + 28)
            chip(img, ink, cx, y + 20, s, self.rgb["line"], self.rgb["text"], "label", h=40)
        else:
            s = f"Alarm at {self.alarm_m:.0f} m"
            cx -= int(ink.width(s, "label", "Semibold") + 28)
            chip(img, ink, cx, y + 20, s, self.rgb["alarm"], self.rgb["dark"], "label", h=40)

    def _caption(self, img):
        x, y, w, h = self.cap_box
        text, tag = self.caption
        end = self.ink.put(img, x + 40, y + 10, text, self.rgb["text"], "caption", "Semibold")
        if tag == "alarm":
            return
        if tag is not None:
            tc = self.rgb["dark"] if tag in self.sc["dark_text_bands"] else (255, 255, 255)
            chip(img, self.ink, int(end + 20), y + 8, tag, self.band_rgb[tag], tc)


def render_end(end: dict, road: Road, cfg: dict) -> np.ndarray:
    """The result screen: segments, the repair plans at the budget, and detection vs truth."""
    sc = cfg["screen"]
    rgb = {k: tuple(v) for k, v in sc["rgb"].items()}
    band_rgb = {k: tuple(v) for k, v in sc["band_rgb"].items()}
    ink, t, m = Ink(sc), rgb["text"], rgb["muted"]
    W, H = sc["size"]
    img = np.empty((H, W, 3), np.uint8)
    img[:] = rgb["bg"]
    ch = sc["caption_h"]
    img[H - ch :] = rgb["panel"]
    segs, rep, det = end["segments"], end["repair"], end["detection"]

    def band_chip(x, y, pci, band, size="label"):
        tc = rgb["dark"] if band in sc["dark_text_bands"] else (255, 255, 255)
        return chip(img, ink, x, y, f"{pci:.0f}  {band}", band_rgb[band], tc, size, h=40)

    alarm = end["drift_alarm_m"]
    ink.put(img, 60, 36, "Survey complete", t, 48, "Semibold")
    sub = (
        f"{road.preset} road, seed {road.seed} · {road.length_m:.0f} m · {len(segs)} segments · "
        + (f"drift alarm at {alarm:.0f} m" if alarm is not None else "no drift alarm")
    )
    ink.put(img, 60, 104, sub, m, "label")

    # ---- per-segment table ----
    cols = {
        "#": 60,
        "Ground": 120,
        "Counted P · A · L": 330,
        "Vision-estimated PCI": 560,
        "Reference PCI": 830,
        "Optimiser": 1090,
        "Worst-first": 1220,
    }
    y0 = 172
    for name, cx in cols.items():
        ink.put(img, cx, y0, name, m, "small", "Medium")
    row_h = min(58, (H - ch - 40 - (y0 + 36)) // max(1, len(segs)))
    chosen = {k: set(v["chosen"]) for k, v in rep["plans"].items()}
    worst = set(rep["worst"])
    for r, s in enumerate(segs):
        y = y0 + 36 + r * row_h
        if r % 2 == 0:
            img[y - 6 : y + row_h - 6, 40:1340] = rgb["panel"]
        cy = y + 4
        ink.put(img, cols["#"], cy, str(s["index"] + 1), t, "label", "Semibold")
        ink.put(img, cols["Ground"], cy, f"{s['x0_m']:.0f}–{s['x1_m']:.0f} m", t, "label")
        c = s["counts"]
        counted = f"{c['pothole']} · {c['alligator_crack']} · {c['linear_crack']}"
        ink.put(img, cols["Counted P · A · L"], cy, counted, t, "label")
        band_chip(cols["Vision-estimated PCI"], y - 2, s["vision_estimated_pci"], s["band"])
        right = band_chip(cols["Reference PCI"], y - 2, s["pci_ref"], s["band_ref"])
        if s["index"] in worst:
            ink.put(img, right + 10, cy, f"worst {rep_n(rep)}", m, "small")
        for name in ("optimiser", "worst-first"):
            cx = cols["Optimiser" if name == "optimiser" else "Worst-first"] + 40
            if s["index"] in chosen[name]:
                cv2.circle(img, (cx, y + 18), 11, t, -1, cv2.LINE_AA)
            else:
                cv2.circle(img, (cx, y + 18), 11, rgb["line"], 2, cv2.LINE_AA)

    # ---- repair plan ----
    x = 1400
    ink.put(img, x, 172, "Repair plan", t, "title", "Semibold")
    ink.put(
        img,
        x,
        212,
        f"budget {rep['budget_frac']:.0%} of the cost of repairing every segment",
        m,
        "small",
    )
    for k, (name, label) in enumerate((("optimiser", "Optimiser"), ("worst-first", "Worst-first"))):
        p, y = rep["plans"][name], 262 + k * 176
        ink.put(img, x, y, label, t, "body", "Semibold")
        ids = ", ".join(str(i + 1) for i in p["chosen"]) or "none"
        ink.put(img, x, y + 38, f"repairs segments {ids}", m, "small")
        ink.put(img, x, y + 68, f"{p['true_benefit']:.0f}", t, "count", "Medium")
        ink.put(img, x, y + 124, "true benefit", m, "small")
        ink.put(img, x + 200, y + 68, f"{p['worst_covered']} of {rep_n(rep)}", t, "count", "Medium")
        ink.put(img, x + 200, y + 124, f"of the true worst {rep_n(rep)}", m, "small")

    # ---- detection vs ground truth ----
    y = 640
    ink.put(img, x, y, "Detection vs ground truth", t, "title", "Semibold")
    ink.put(img, x, y + 40, "confirmed tracks, both lanes, IoU > 0.1", m, "small")
    ink.put(img, x + 200, y + 80, "recall", m, "small", "Medium")
    ink.put(img, x + 330, y + 80, "false alarms/km", m, "small", "Medium")
    for k, cls in enumerate(("pothole", "alligator_crack", "linear_crack")):
        d, ry = det["per_class"][cls], y + 112 + k * 62
        cv2.circle(
            img, (x + 9, ry + 18), 9, tuple(cfg["drive"]["colours_bgr"][cls][::-1]), -1, cv2.LINE_AA
        )
        ink.put(img, x + 28, ry, NAMES[cls], t, "label")
        rec = "n/a" if d["recall"] is None else f"{d['recall']:.0%}"
        ink.put(img, x + 200, ry - 6, rec, t, "body", "Semibold")
        ink.put(img, x + 200, ry + 30, f"{d['hit']} of {d['instances']}", m, "small")
        fa = "n/a" if d["false_alarms_per_km"] is None else f"{d['false_alarms_per_km']:.1f}"
        ink.put(img, x + 330, ry - 6, fa, t, "body", "Semibold")
        ink.put(img, x + 330, ry + 30, f"{d['false_alarm_tracks']} tracks", m, "small")

    y = H - ch
    ink.put(
        img,
        40,
        y + 10,
        "A simulated road scored by the real pipeline: a demonstration, not a field result",
        t,
        "caption",
        "Semibold",
    )
    ink.put(img, 40, y + 64, honesty(road, cfg), m, "small")
    return cv2.cvtColor(img, cv2.COLOR_RGB2BGR)


def rep_n(rep: dict) -> int:
    return len(rep["worst"])
