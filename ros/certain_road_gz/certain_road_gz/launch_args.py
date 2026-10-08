"""What world.launch.py works out before it starts anything: the world, the camera, the spawn.

Free of ROS imports, so tests/test_gazebo_launch.py runs it where ROS is absent (CI). It
reads only files the package installs (config/car.yaml, the car's model.sdf) and the
exported world folder (world.json), so it works on any machine those were copied to.
"""

from __future__ import annotations

import json
import math
import os
import xml.etree.ElementTree as ET
from pathlib import Path

WORLDS_ENV = "CERTAIN_ROAD_GZ_WORLDS"
# Relative to the working directory: the repository root on the Jetson. Elsewhere, set
# CERTAIN_ROAD_GZ_WORLDS or pass world:=<folder>.
DEFAULT_WORLDS = "runs/gazebo"
# REP 103: an optical frame has z forward, x right, y down. From a body frame (x forward,
# y left, z up) that is roll -pi/2, then yaw -pi/2.
OPTICAL_RPY = (-math.pi / 2, 0.0, -math.pi / 2)


def _absolute(path: str, cwd: Path) -> Path:
    p = Path(path).expanduser()
    return p if p.is_absolute() else cwd / p


def world_dir(world: str, worlds_dir: str, preset: str, seed: str, cwd: Path) -> Path:
    """The exported world folder: `world` if given (a folder or its world.sdf), else
    <worlds_dir or $CERTAIN_ROAD_GZ_WORLDS or runs/gazebo>/<preset>_seed<seed>."""
    if world:
        p = _absolute(world, cwd)
        if p.is_file():
            p = p.parent
    else:
        root = worlds_dir or os.environ.get(WORLDS_ENV) or DEFAULT_WORLDS
        p = _absolute(root, cwd) / f"{preset}_seed{seed}"
    if not (p / "world.sdf").is_file():
        raise FileNotFoundError(
            f"no world.sdf in {p}. Export one on a machine with the repository "
            f"(python -m sim.gazebo.export --preset {preset} --seed {seed}) and copy the "
            "folder here, or pass world:=<folder>."
        )
    return p.resolve()


def world_meta(folder: Path) -> dict:
    return json.loads((folder / "world.json").read_text())


def _camera(root: ET.Element) -> ET.Element:
    sensor = root.find(".//sensor[@type='camera']")
    if sensor is None:
        raise ValueError("the car's SDF has no camera sensor")
    return sensor


def with_camera(sdf_text: str, w: str = "", h: str = "", rate_hz: str = "") -> str:
    """The car's SDF with the camera's width, height and rate replaced; '' keeps a value."""
    root = ET.fromstring(sdf_text)
    sensor = _camera(root)
    if rate_hz:
        sensor.find("update_rate").text = str(float(rate_hz))
    image = sensor.find("camera/image")
    if w:
        image.find("width").text = str(int(w))
    if h:
        image.find("height").text = str(int(h))
    return '<?xml version="1.0"?>\n' + ET.tostring(root, encoding="unicode") + "\n"


def camera_settings(sdf_text: str) -> dict:
    """(width, height, rate) the SDF's camera will run at."""
    sensor = _camera(ET.fromstring(sdf_text))
    image = sensor.find("camera/image")
    return {
        "w": int(image.find("width").text),
        "h": int(image.find("height").text),
        "rate_hz": float(sensor.find("update_rate").text),
    }


def spawn_args(meta: dict, car: dict, sdf_file: Path) -> list[str]:
    """Arguments for `ros_gz_sim create`: the car in the driving lane, facing along the road."""
    s = meta["spawn"]
    return [
        "-world", meta["world_name"],
        "-file", str(sdf_file),
        "-name", car["model_name"],
        "-x", str(s["x"]),
        "-y", str(s["y"]),
        "-z", str(car["spawn_z_m"]),
        "-Y", str(s["yaw"]),
    ]  # fmt: skip


def static_tf_args(car: dict) -> list[list[str]]:
    """`static_transform_publisher` arguments: base -> camera, camera -> optical."""
    f = car["frames"]
    (x, y, z), (roll, pitch, yaw) = car["camera_xyz"], car["camera_rpy"]

    def tf(xyz, rpy, parent, child):
        out = []
        for key, value in zip(("x", "y", "z", "roll", "pitch", "yaw"), (*xyz, *rpy), strict=True):
            out += [f"--{key}", repr(float(value))]
        return out + ["--frame-id", parent, "--child-frame-id", child]

    return [
        tf((x, y, z), (roll, pitch, yaw), f["base"], f["camera"]),
        tf((0.0, 0.0, 0.0), OPTICAL_RPY, f["camera"], f["optical"]),
    ]


def physics_step(world_sdf: Path) -> float:
    """The world file's physics step, kept when only the real-time factor changes."""
    step = ET.parse(world_sdf).getroot().find(".//physics/max_step_size")
    if step is None:
        raise ValueError(f"{world_sdf} names no physics max_step_size")
    return float(step.text)


def set_physics_script(
    world_name: str, step_s: float, rtf: float, tries: int, wait_s: float
) -> str:
    """A shell loop that sets the running world's real-time factor through gz-sim's
    UserCommands service, retrying until the world answers. The SDF stays untouched."""
    call = (
        f"gz service -s /world/{world_name}/set_physics --reqtype gz.msgs.Physics "
        f"--reptype gz.msgs.Boolean --timeout {int(wait_s * 1000)} "
        f"--req 'max_step_size: {step_s!r}, real_time_factor: {rtf!r}'"
    )
    return (
        f"for i in $(seq {tries}); do "
        f'out=$({call} 2>&1); case "$out" in *true*) echo "real_time_factor {rtf!r} set"; '
        f"exit 0;; esac; sleep {wait_s!r}; done; echo 'set_physics: no answer' >&2; exit 1"
    )
