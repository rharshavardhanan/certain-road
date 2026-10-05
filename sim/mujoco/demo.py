"""MuJoCo survey demo CLI.

    uv run python -m sim.mujoco.demo --preset poor --seed 0 --screenshot runs/mujoco/step1.png
    uv run python -m sim.mujoco.demo --preset poor --seed 0 --ground-truth runs/mujoco/gt.json

Step 1 of the build: the scene and one camera frame. The live loop comes next.
"""

from __future__ import annotations

import argparse
import time
from pathlib import Path

import cv2

from sim.mujoco import road as road_mod
from sim.mujoco import textures

PRESETS = ("good", "moderate", "poor", "mixed", "random")


def make_road(preset: str, seed: int) -> tuple[road_mod.Road, dict]:
    cfg = road_mod.load_config()
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
    ap.add_argument("--ground-truth", type=Path)
    ap.add_argument("--screenshot", type=Path)
    ap.add_argument("--at", type=float, help="metres along the road; default: the busiest view")
    args = ap.parse_args()
    road, cfg = make_road(args.preset, args.seed)
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
        cv2.imwrite(str(args.screenshot), cv2.cvtColor(img, cv2.COLOR_RGB2BGR))
        print(
            f"scene built in {t1 - t0:.1f} s; frame at {x:.0f} m in {time.time() - t1:.2f} s "
            f"-> {args.screenshot} {img.shape[1]}x{img.shape[0]}"
        )


if __name__ == "__main__":
    main()
