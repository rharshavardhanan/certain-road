"""Export one seeded road as a Gazebo Harmonic world folder.

    python -m sim.gazebo.export --preset poor --seed 0

Builds the MuJoCo demo's scene for the road (sim/mujoco/scene.py, under gazebo.yaml's `look`)
and converts it (sim/gazebo/convert.py), so the Gazebo road is the MuJoCo road: the same
generator and seed, the same baked photo textures, the same 3D potholes. Writes
runs/gazebo/<preset>_seed<seed>/ (gitignored):

- `world.sdf`: physics, light, and one static road model. Every path in it is relative.
- `meshes/*.obj`, `textures/*.png`: road tiles (visual and collision), shoulders, ground,
  and the merged kerbs, poles, wall, signs and trees.
- `ground_truth.json`: `Road.save`, byte-identical to the MuJoCo demo's for the same road.
- `world.json`: where the car starts, the road's extent, sizes and timings, the credits.

The folder is self-contained: copy it to any machine with Gazebo Harmonic and the
certain_road_gz package, and `ros2 launch certain_road_gz world.launch.py world:=<folder>`
loads it. This module needs the texture photos (data/raw/trial_textures) and MuJoCo; the
machine that loads the world needs neither.
"""

from __future__ import annotations

import argparse
import json
import resource
import time
from pathlib import Path

import cv2
import mujoco
import numpy as np
import yaml

from certain_road.core.paths import repo_root
from sim.gazebo import meshes
from sim.gazebo.convert import ColourPart, TexturedPart, convert
from sim.gazebo.world import manifest, world_sdf
from sim.mujoco.road import load_config

CONFIG = repo_root() / "configs/sim/gazebo.yaml"


def load_gz() -> dict:
    return yaml.safe_load(CONFIG.read_text())


def world_folder(preset: str, seed: int, gz: dict | None = None) -> Path:
    gz = gz or load_gz()
    return repo_root() / gz["out_dir"] / f"{preset}_seed{seed}"


def write_texture(path: Path, rgb: np.ndarray, ex: dict) -> int:
    """Save MuJoCo's RGB pixels row for row (row 0 stays texture v = 0); returns bytes."""
    if ex["texture_scale"] != 1.0:
        rgb = cv2.resize(
            rgb, None, fx=ex["texture_scale"], fy=ex["texture_scale"], interpolation=cv2.INTER_AREA
        )
    path.parent.mkdir(parents=True, exist_ok=True)
    bgr = cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR)
    if ex["texture_format"] == "png":
        cv2.imwrite(str(path), bgr, [cv2.IMWRITE_PNG_COMPRESSION, ex["png_compression"]])
    else:
        cv2.imwrite(str(path), bgr, [cv2.IMWRITE_JPEG_QUALITY, ex["jpg_quality"]])
    return path.stat().st_size


def floor_z(textured: list[TexturedPart]) -> float:
    """The lowest drawn surface: MuJoCo's ground plane, below the deepest pothole."""
    lows = []
    for p in textured:
        rot = np.zeros(9)
        mujoco.mju_quat2Mat(rot, p.quat)
        lows.append(float((p.mesh.v @ rot.reshape(3, 3).T)[:, 2].min() + p.pos[2]))
    return min(lows)


def write_world(
    out: Path,
    textured: list[TexturedPart],
    coloured: list[ColourPart],
    look: dict,
    gz: dict,
    road_box: dict,
) -> dict:
    """Mesh, texture and SDF files into `out`; returns their counts and sizes."""
    ex = gz["export"]
    ext = "png" if ex["texture_format"] == "png" else "jpg"
    files: dict[str, tuple[str, str | None]] = {}
    size = {"meshes": 0, "textures": 0}
    tris = {"visual": 0, "collision": 0}
    written: set[str] = set()
    for p in textured:
        mesh_rel, tex_rel = f"meshes/{p.name}.obj", f"textures/{p.material}.{ext}"
        size["meshes"] += meshes.write_obj(out / mesh_rel, p.mesh, ex["decimals"])
        if tex_rel not in written:
            size["textures"] += write_texture(out / tex_rel, p.texture, ex)
            written.add(tex_rel)
        files[p.name] = (mesh_rel, tex_rel)
        tris["visual"] += len(p.mesh.f)
        tris["collision"] += len(p.mesh.f) if p.collide else 0
    for p in coloured:
        mesh_rel = f"meshes/{p.name}.obj"
        size["meshes"] += meshes.write_obj(out / mesh_rel, p.mesh, ex["decimals"])
        files[p.name] = (mesh_rel, None)
        tris["visual"] += len(p.mesh.f)
    parts = manifest(textured, coloured, files)
    (out / "parts.json").write_text(json.dumps({"road_box": road_box, "parts": parts}, indent=1))
    (out / "world.sdf").write_text(world_sdf(parts, look, gz, road_box))
    return {
        "bytes": size,
        "triangles": tris,
        "visuals": len(textured) + len(coloured),
        "collision_meshes": sum(p.collide for p in textured),
        "merged_primitives": sum(p.count for p in coloured),
        "textures": len(written),
    }


def export(preset: str, seed: int, out: Path | None = None) -> dict:
    from sim.mujoco.demo import make_road
    from sim.mujoco.scene import build

    gz = load_gz()
    road, look = make_road(preset, seed, gz["look"])
    out = out or world_folder(preset, seed, gz)
    out.mkdir(parents=True, exist_ok=True)
    t0 = time.perf_counter()
    model, cam = build(road, look)
    t1 = time.perf_counter()
    textured, coloured = convert(model, gz["export"])
    t2 = time.perf_counter()
    del model
    road_box = {
        "length_m": road.length_m,
        "half_width_m": road.lane_width_m,
        "floor_z": floor_z(textured),
    }
    stats = write_world(out, textured, coloured, look, gz, road_box)
    t3 = time.perf_counter()
    road.save(out / "ground_truth.json")
    meta = {
        "preset": preset,
        "seed": seed,
        "look": gz["look"],
        "world_name": gz["world_name"],
        "world_sdf": "world.sdf",
        "ground_truth": "ground_truth.json",
        "road": {
            "length_m": road.length_m,
            "lane_width_m": road.lane_width_m,
            "drive_lane_y": road.drive_lane_y,
            "instances": {
                c: sum(i.cls == c for i in road.instances)
                for c in ("linear_crack", "alligator_crack", "pothole")
            },
            "floor_z": round(road_box["floor_z"], 4),
        },
        # keep left (India): the car starts in the left lane, facing +x along the road
        "spawn": {"x": gz["vehicle"]["spawn"]["x_m"], "y": road.drive_lane_y, "yaw": 0.0},
        "design_camera": {k: round(float(v), 6) for k, v in cam.items()},
        "export": {
            **stats,
            "scene_build_s": round(t1 - t0, 1),
            "convert_s": round(t2 - t1, 1),
            "write_s": round(t3 - t2, 1),
            # Linux reports ru_maxrss in KiB
            "peak_rss_mb": round(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024),
        },
        "credits": look["credits"],
    }
    (out / "world.json").write_text(json.dumps(meta, indent=1))
    return meta


def rewrite_sdf(out: Path) -> None:
    """world.sdf again from parts.json and today's config: new light or physics, same road.

    Needs neither MuJoCo's scene build nor the texture photos, so it takes a second.
    """
    gz = load_gz()
    saved = json.loads((out / "parts.json").read_text())
    look = load_config(gz["look"])
    (out / "world.sdf").write_text(world_sdf(saved["parts"], look, gz, saved["road_box"]))


def main() -> None:
    from sim.mujoco.demo import PRESETS

    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--preset", choices=PRESETS, default="poor")
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument(
        "--out", type=Path, help="world folder (default: runs/gazebo/<preset>_seed<seed>)"
    )
    ap.add_argument(
        "--sdf-only", action="store_true", help="rewrite world.sdf from parts.json and the config"
    )
    args = ap.parse_args()
    out = args.out or world_folder(args.preset, args.seed)
    if args.sdf_only:
        rewrite_sdf(out)
        print(f"world -> {out / 'world.sdf'}")
        return
    meta = export(args.preset, args.seed, args.out)
    print(json.dumps(meta["export"], indent=1))
    print(f"world -> {out / 'world.sdf'}")


if __name__ == "__main__":
    main()
