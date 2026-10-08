"""Write the Gazebo world SDF for converted parts: one static road model, light, physics.

Every file the world names is a path relative to the world file (`meshes/…`, `textures/…`),
which Gazebo resolves against the world file's own folder. The exported folder can therefore
be copied to another machine and loaded there as it is. The vehicle is not in the world: the
launch file spawns it (ros/certain_road_gz), so its camera resolution and rate can be set at
launch without re-exporting the road.

This module writes text. It does not run Gazebo and does not know where the parts came from.
"""

from __future__ import annotations

import math
import xml.etree.ElementTree as ET

import numpy as np

from sim.gazebo.convert import ColourPart, TexturedPart

SDF_VERSION = "1.10"


def rpy(quat) -> tuple[float, float, float]:
    """(roll, pitch, yaw) of a w-x-y-z quaternion: SDF's fixed-axis X, Y, Z order."""
    w, x, y, z = (float(q) for q in quat)
    roll = math.atan2(2 * (w * x + y * z), 1 - 2 * (x * x + y * y))
    pitch = math.asin(max(-1.0, min(1.0, 2 * (w * y - z * x))))
    yaw = math.atan2(2 * (w * z + x * y), 1 - 2 * (y * y + z * z))
    return roll, pitch, yaw


def fmt(values, decimals: int = 6) -> str:
    return " ".join(f"{float(v):.{decimals}f}".rstrip("0").rstrip(".") or "0" for v in values)


def sub(parent: ET.Element, tag: str, text=None, **attrib) -> ET.Element:
    e = ET.SubElement(parent, tag, {k: str(v) for k, v in attrib.items()})
    if text is not None:
        e.text = text if isinstance(text, str) else fmt(np.atleast_1d(text))
    return e


def plugin(parent: ET.Element, filename: str, name: str, **params) -> ET.Element:
    p = sub(parent, "plugin", filename=filename, name=name)
    for k, v in params.items():
        if isinstance(v, dict):
            inner = sub(p, k)
            for k2, v2 in v.items():
                sub(inner, k2, v2 if isinstance(v2, str) else fmt(np.atleast_1d(v2)))
        else:
            sub(p, k, v if isinstance(v, str) else fmt(np.atleast_1d(v)))
    return p


def _mesh_geometry(parent: ET.Element, uri: str) -> None:
    sub(sub(sub(parent, "geometry"), "mesh"), "uri", uri)


def _friction(parent: ET.Element, mu: float) -> None:
    ode = sub(sub(sub(parent, "surface"), "friction"), "ode")
    sub(ode, "mu", mu)
    sub(ode, "mu2", mu)


def _pbr(material: ET.Element, finish: dict, albedo: str | None = None) -> None:
    metal = sub(sub(material, "pbr"), "metal")
    if albedo is not None:
        sub(metal, "albedo_map", albedo)
    sub(metal, "roughness", finish["roughness"])
    sub(metal, "metalness", finish["metalness"])


def manifest(
    textured: list[TexturedPart],
    coloured: list[ColourPart],
    files: dict[str, tuple[str, str | None]],
) -> list[dict]:
    """What the world file needs of each part, as JSON-able rows (export saves it as parts.json).

    `files`: part name -> (mesh path, texture path or None), relative to the world file.
    """
    rows = [
        {
            "name": p.name,
            "mesh": files[p.name][0],
            "texture": files[p.name][1],
            "pose": [round(float(v), 7) for v in (*p.pos, *rpy(p.quat))],
            "rgba": [float(c) for c in p.rgba],
            "collide": p.collide,
        }
        for p in textured
    ]
    return rows + [
        {
            "name": p.name,
            "mesh": files[p.name][0],
            "texture": None,
            "pose": None,
            "rgba": [float(c) for c in p.rgba],
            "collide": False,
        }
        for p in coloured
    ]


def linear(rgba, gamma: float) -> list[float]:
    """A MuJoCo colour (a display value) in the linear space Ogre 2 lights in; alpha kept."""
    return [float(c) ** gamma for c in rgba[:3]] + [float(rgba[3])]


def world_sdf(parts: list[dict], look: dict, gz: dict, road_box: dict) -> str:
    """The world file's text, from `manifest` rows.

    `look`: the MuJoCo look's config (sun, sky, ambient, kerbs); `gz`: gazebo.yaml.
    `road_box`: {length_m, half_width_m, floor_z} of the carriageway: the kerb collision
    boxes run along it, and the catch plane sits at the lowest drawn geometry (MuJoCo's ground).
    """
    rd, ph = gz["render"], gz["physics"]
    sc = look["scene"]
    sdf = ET.Element("sdf", version=SDF_VERSION)
    world = sub(sdf, "world", name=gz["world_name"])
    sub(world, "gravity", [0.0, 0.0, -ph["gravity_mps2"]])
    physics = sub(world, "physics", name="default", type="ignored")
    sub(physics, "max_step_size", ph["max_step_size_s"])
    sub(physics, "real_time_factor", ph["real_time_factor"])
    plugin(
        world,
        "gz-sim-physics-system",
        "gz::sim::systems::Physics",
        engine={"filename": ph["plugin"]},
    )
    plugin(world, "gz-sim-user-commands-system", "gz::sim::systems::UserCommands")
    plugin(world, "gz-sim-scene-broadcaster-system", "gz::sim::systems::SceneBroadcaster")
    plugin(world, "gz-sim-sensors-system", "gz::sim::systems::Sensors", render_engine=rd["engine"])
    scene = sub(world, "scene")
    ambient = sc["ambient"] * rd["ambient_gain"]
    sub(scene, "ambient", [ambient, ambient, ambient, 1.0])
    sub(scene, "background", [*sc["sky"]["horizon"], 1.0])
    sub(scene, "shadows", "true" if rd["cast_shadows"] else "false")
    sub(scene, "grid", "false")
    sun = sub(world, "light", type="directional", name="sun")
    sub(sun, "cast_shadows", "true" if rd["cast_shadows"] else "false")
    sub(sun, "diffuse", [1.0, 1.0, 1.0, 1.0])  # SDF clamps colours to 1: strength is intensity
    sub(sun, "intensity", sc["sun_diffuse"] * rd["sun_gain"])
    sub(sun, "specular", [rd["sun_specular"]] * 3 + [1.0])
    d = np.asarray(sc["sun_dir"], float)
    sub(sun, "direction", d / np.linalg.norm(d))

    model = sub(world, "model", name="road")
    sub(model, "static", "true")
    link = sub(model, "link", name="surface")
    for p in parts:
        vis = sub(link, "visual", name=p["name"])
        if p["pose"] is not None:
            sub(vis, "pose", p["pose"])
        _mesh_geometry(vis, p["mesh"])
        mat = sub(vis, "material")
        if p["texture"] is not None:  # the texture carries the colour; it is decoded as sRGB
            sub(mat, "diffuse", p["rgba"])
            sub(mat, "specular", [rd["sun_specular"]] * 3 + [1.0])
            _pbr(mat, rd["road"], p["texture"])
        else:
            rgba = linear(p["rgba"], rd["colour_gamma"])
            sub(mat, "ambient", rgba)
            sub(mat, "diffuse", rgba)
            _pbr(mat, rd["props"])
        if p["collide"]:
            col = sub(link, "collision", name=f"{p['name']}_collision")
            if p["pose"] is not None:
                sub(col, "pose", p["pose"])
            _mesh_geometry(col, p["mesh"])
            _friction(col, ph["friction"]["road"])
    kerb = look["road"]["kerb"]
    if ph["kerb_collision"]:
        length, half = road_box["length_m"], road_box["half_width_m"]
        for side, name in ((1, "kerb_left"), (-1, "kerb_right")):
            col = sub(link, "collision", name=name)
            y = side * (half + kerb["width_m"] / 2)
            sub(col, "pose", [length / 2, y, kerb["height_m"] / 2, 0, 0, 0])
            sub(
                sub(sub(col, "geometry"), "box"),
                "size",
                [length, kerb["width_m"], kerb["height_m"]],
            )
            _friction(col, ph["friction"]["kerb"])
    if ph["catch_plane"]:
        col = sub(link, "collision", name="catch_plane")
        sub(col, "pose", [0, 0, road_box["floor_z"], 0, 0, 0])
        sub(sub(sub(col, "geometry"), "plane"), "normal", [0, 0, 1])
        _friction(col, ph["friction"]["road"])
    ET.indent(sdf)
    return '<?xml version="1.0"?>\n' + ET.tostring(sdf, encoding="unicode") + "\n"
