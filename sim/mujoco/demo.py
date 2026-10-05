"""MuJoCo survey demo CLI.

    uv run python -m sim.mujoco.demo --preset poor --seed 0 --screenshot runs/mujoco/step1.png
    uv run python -m sim.mujoco.demo --preset poor --seed 0 --ground-truth runs/mujoco/gt.json
    uv run python -m sim.mujoco.demo --preset poor --seed 0 --drive [--headless] [--until-m 120]

`--drive` runs the drive loop with the real detectors (sim/mujoco/drive.py) and writes
runs/mujoco/<preset>_seed<seed>/: ground_truth.json, detections.jsonl, drive_summary.json.
"""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

import cv2
import numpy as np

from sim.mujoco import road as road_mod
from sim.mujoco import textures

PRESETS = ("good", "moderate", "poor", "mixed", "random")


def make_road(preset: str, seed: int, look: str | None = None) -> tuple[road_mod.Road, dict]:
    cfg = road_mod.load_config(look)
    cat = textures.catalogue(cfg["surface"]["flatten_sigma_frac"])
    return road_mod.generate(preset, seed, cat, cfg), cfg


def busiest_view(road: road_mod.Road, near: float = 4.0, far: float = 16.0) -> float:
    """Camera position whose view window holds the most ground-truth instances."""
    best, best_x = -1, 30.0
    for x in range(int(road.length_m - far)):
        n = sum(1 for i in road.instances if x + near <= i.x_m <= x + far)
        if n > best:
            best, best_x = n, float(x)
    return best_x


def showcase_view(road: road_mod.Road, lo: float = 9.5, hi: float = 11.0) -> float | None:
    """The 10 m view of the largest driving-lane pothole with a crack in the same window.

    The pothole may sit inside the crack patch, as most do on a failed road.
    """
    best, best_x = 0.0, None
    lane = [i for i in road.instances if abs(i.y_m - road.drive_lane_y) < road.lane_width_m / 2]
    for x in range(int(road.length_m - hi)):
        pots = [i for i in lane if i.cls == "pothole" and lo <= i.x_m - x <= hi]
        cracks = [i for i in road.instances if i.cls != "pothole" and lo - 1 <= i.x_m - x <= hi + 1]
        if pots and cracks:
            score = max(p.length_m for p in pots) + 0.1 * max(c.area_m2 for c in cracks)
            if score > best:
                best, best_x = score, float(x)
    return best_x


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--preset", choices=PRESETS, default="poor")
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument(
        "--look",
        help="v1: the simulator at the demo-v1 tag; v2: 3D potholes, surface detail, harsher light",
    )
    ap.add_argument("--ground-truth", type=Path)
    ap.add_argument("--screenshot", type=Path)
    ap.add_argument("--at", type=float, help="metres along the road; default: the busiest view")
    ap.add_argument("--drive", action="store_true", help="drive (the default with no other action)")
    ap.add_argument("--headless", action="store_true", help="no window; write the logs only")
    ap.add_argument("--until-m", type=float, help="stop the drive early, for a quick check")
    ap.add_argument("--record", type=Path, help="also write the screen to this .mp4, in real time")
    ap.add_argument("--still", type=Path, help="save the last screen frame as a PNG")
    ap.add_argument("--budget-frac", type=float, help="repair budget, share of the full cost")
    ap.add_argument("--end-only", action="store_true", help="redraw the end screen of a run")
    args = ap.parse_args()
    # The plain command drives: the brief's `--preset poor --seed 0` opens and runs.
    args.drive = args.drive or not (args.screenshot or args.ground_truth or args.end_only)
    look = args.look or road_mod.load_config()["default_look"]
    road, cfg = make_road(args.preset, args.seed, look)
    counts = {c: sum(i.cls == c for i in road.instances) for c in road_mod.CLASSES}
    print(
        f"{args.preset} seed {args.seed}: {road.length_m:.0f} m, "
        f"{len(road.instances)} instances {counts}"
    )
    if args.ground_truth:
        road.save(args.ground_truth)
    if args.screenshot:
        from sim.mujoco.camera import Camera
        from sim.mujoco.scene import build

        t0 = time.time()
        model, cam = build(road, cfg)
        t1 = time.time()
        camera = Camera(model, cam, cfg, args.seed, road.drive_lane_y)
        x = args.at if args.at is not None else (showcase_view(road) or busiest_view(road))
        img = camera.frame(x)
        args.screenshot.parent.mkdir(parents=True, exist_ok=True)
        cv2.imwrite(str(args.screenshot), img)  # Camera.frame returns BGR
        print(
            f"scene built in {t1 - t0:.1f} s; frame at {x:.0f} m in {time.time() - t1:.2f} s "
            f"-> {args.screenshot} {img.shape[1]}x{img.shape[0]}"
        )

    if args.drive or args.end_only:
        from certain_road.core.paths import repo_root
        from sim.mujoco.evaluate import summarise
        from sim.mujoco.screen import render_end

        tag = "" if look == "v1" else f"_{look}"  # v1 keeps the run directories it always had
        out = repo_root() / cfg["out_dir"] / f"{args.preset}_seed{args.seed}{tag}"
        live = None
        if not args.headless or args.record or args.still:
            live = Live(road, cfg, window=not args.headless, record=args.record)
        if args.drive:
            from sim.mujoco.drive import run

            summary = run(road, cfg, out, show=live, until_m=args.until_m)
            print(json.dumps(summary, indent=1))
            if live is not None and args.still and live.last is not None:
                args.still.parent.mkdir(parents=True, exist_ok=True)
                cv2.imwrite(str(args.still), live.last)
        end = summarise(road, cfg, out, args.budget_frac)
        img = render_end(end, road, cfg)
        cv2.imwrite(str(out / "end_screen.png"), img)
        print(json.dumps({k: end[k] for k in ("detection", "repair", "drift_alarm_m")}, indent=1))
        print(f"end screen -> {out / 'end_screen.png'}")
        if live is not None:
            live.hold(img, cfg["end"]["hold_s"])
            live.close()


class Live:
    """The four-panel screen, shown in a window and/or recorded. Built on the first frame."""

    NAME = "certain-road survey demo"

    def __init__(self, road, cfg: dict, window: bool, record: Path | None):
        self.road, self.cfg, self.window, self.record = road, cfg, window, record
        self.screen = self.writer = None
        self.last: np.ndarray | None = None
        if window:
            cv2.namedWindow(self.NAME, cv2.WINDOW_NORMAL)
            cv2.resizeWindow(self.NAME, *cfg["screen"]["size"])

    def __call__(self, rec, bgr, drv) -> bool:
        from sim.mujoco.screen import Screen

        if self.screen is None:
            self.screen = Screen(
                self.road, self.cfg, drv.cam, sum(drv.sampled), drv.survey.per_segment
            )
            if self.record is not None:
                self.record.parent.mkdir(parents=True, exist_ok=True)
                fps = drv.cam["speed_mps"] / (drv.xs[1] - drv.xs[0])  # real time
                self.fps = fps
                self.writer = cv2.VideoWriter(
                    str(self.record),
                    cv2.VideoWriter_fourcc(*"mp4v"),
                    fps,
                    tuple(self.cfg["screen"]["size"]),
                )
        self.last = self.screen.update(rec, bgr, drv)
        return self.show(self.last)

    def show(self, img: np.ndarray, wait_ms: int = 1) -> bool:
        if self.writer is not None:
            self.writer.write(img)
        if not self.window:
            return True
        cv2.imshow(self.NAME, img)
        return cv2.waitKey(wait_ms) not in (27, ord("q"))

    def hold(self, img: np.ndarray, seconds: float) -> None:
        """Hold the end screen: `seconds` of it in a recording; in a window, until a key."""
        if self.writer is not None:
            for _ in range(round(self.fps * seconds)):
                self.writer.write(img)
        if self.window:
            cv2.imshow(self.NAME, img)
            cv2.waitKey(0)

    def close(self) -> None:
        if self.writer is not None:
            self.writer.release()
        if self.window:
            cv2.destroyAllWindows()


if __name__ == "__main__":
    main()
