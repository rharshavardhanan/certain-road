"""The camera car as SDF: a hatchback with Ackermann steering, suspension and the design camera.

- **Chassis** (`base_link`): the sprung mass, a box, its origin at its centre of mass. The
  model frame is `base_link`, so the true odometry (OdometryPublisher, 3D) is the body's pose.
- **Suspension**: each corner hangs on a prismatic joint along the body's z with a spring and
  a damper, sized from a ride frequency and a damping ratio (`vehicle.suspension`). The
  spring's rest position is set so the static load leaves every joint at 0, which puts the
  body at `cg_height_m` and the camera at the design height, less what the tyre contacts give
  (measured on the Jetson: body 6 mm low at cruise, so the camera rides at 1.294 m).
- **Steering and drive**: gz-sim's AckermannSteering steers the two front hubs and drives the
  rear wheels from a Twist (linear.x m/s, angular.z rad/s), as RosTransport sends it.
- **Camera**: the design camera of configs/project.yaml (1.3 m, 10 deg down, HFOV 1.2 rad,
  1280x720), at the front bumper so no bonnet is in view, with MuJoCo's sensor noise.

The SDF is written into ros/certain_road_gz by sim/gazebo/package.py and committed, so the
package needs nothing from this repository at run time. Not here: tyre slip models, engine,
brakes; the wheels turn at the commanded speed.
"""

from __future__ import annotations

import math
import xml.etree.ElementTree as ET

from sim.gazebo.world import SDF_VERSION, plugin, sub

CORNERS = {  # name: (front?, side: +1 left)
    "front_left": (True, 1),
    "front_right": (True, -1),
    "rear_left": (False, 1),
    "rear_right": (False, -1),
}


def box_inertia(mass: float, size) -> list[float]:
    lx, ly, lz = size
    return [
        mass * (ly * ly + lz * lz) / 12,
        mass * (lx * lx + lz * lz) / 12,
        mass * (lx * lx + ly * ly) / 12,
    ]


def cylinder_inertia_y(mass: float, radius: float, length: float) -> list[float]:
    """A wheel spinning about y: (ixx, iyy, izz)."""
    side = mass * (3 * radius * radius + length * length) / 12
    return [side, mass * radius * radius / 2, side]


def sphere_inertia(mass: float, radius: float) -> list[float]:
    return [2 * mass * radius * radius / 5] * 3


def suspension(veh: dict, gravity: float) -> dict:
    """Per-corner spring stiffness, damping and rest position, from ride frequency and ratio.

    The prismatic axis is the body's +z, child (hub) relative to parent (body), so a body that
    sinks reads as a positive joint position. A spring force -k (q - q_ref) that holds the
    corner's static load at q = 0 needs q_ref = -load / k.
    """
    s = veh["suspension"]
    corner_mass = veh["chassis"]["mass_kg"] / len(CORNERS)
    k = corner_mass * (2 * math.pi * s["ride_hz"]) ** 2
    c = 2 * s["damping_ratio"] * math.sqrt(k * corner_mass)
    return {
        "stiffness": k,
        "damping": c,
        "reference": -corner_mass * gravity / k,
        "static_sag_m": corner_mass * gravity / k,
    }


def _inertial(link: ET.Element, mass: float, diag) -> None:
    inertial = sub(link, "inertial")
    sub(inertial, "mass", mass)
    inertia = sub(inertial, "inertia")
    for tag, value in zip(("ixx", "iyy", "izz"), diag, strict=True):
        sub(inertia, tag, value)
    for tag in ("ixy", "ixz", "iyz"):
        sub(inertia, tag, 0.0)


def _colour(parent: ET.Element, rgba) -> None:
    mat = sub(parent, "material")
    sub(mat, "ambient", list(rgba))
    sub(mat, "diffuse", list(rgba))


def camera_pose(gz: dict, design: dict) -> list[float]:
    """Camera pose in base_link: x, y, z, roll, pitch, yaw. Positive pitch looks down."""
    veh, cam = gz["vehicle"], gz["camera"]
    return [cam["forward_m"], 0.0, design["height"] - veh["cg_height_m"], 0.0, design["pitch"], 0.0]


def vehicle_sdf(gz: dict, design: dict, noise_sigma_255: float, brake_mps2: float) -> str:
    """The car's model.sdf. `design`: sim.mujoco.scene.design_camera(); noise in 0-255 units;
    `brake_mps2`: the deceleration limit, configs/project.yaml sim.a_brake (the design's)."""
    veh, cam, top = gz["vehicle"], gz["camera"], gz["topics"]
    gravity = gz["physics"]["gravity_mps2"]
    ch, wh = veh["chassis"], veh["wheel"]
    r, cg = wh["radius_m"], veh["cg_height_m"]
    sdf = ET.Element("sdf", version=SDF_VERSION)
    model = sub(sdf, "model", name=veh["name"])
    body = sub(model, "link", name=gz["frames"]["base"])
    size = [ch["length_m"], ch["width_m"], ch["height_m"]]
    _inertial(body, ch["mass_kg"], box_inertia(ch["mass_kg"], size))
    for tag in ("visual", "collision"):
        e = sub(body, tag, name=f"body_{tag}")
        sub(sub(sub(e, "geometry"), "box"), "size", size)
        if tag == "visual":
            _colour(e, veh["rgba"])
    cab = veh["cabin"]
    vis = sub(body, "visual", name="cabin")
    sub(vis, "pose", [-cab["setback_m"], 0, (ch["height_m"] + cab["height_m"]) / 2, 0, 0, 0])
    sub(sub(sub(vis, "geometry"), "box"), "size", [cab["length_m"], ch["width_m"], cab["height_m"]])
    _colour(vis, veh["rgba"])

    pose = camera_pose(gz, design)
    sensor = sub(body, "sensor", name="dashcam", type="camera")
    sub(sensor, "pose", pose)
    sub(sensor, "always_on", "true")
    sub(sensor, "update_rate", cam["rate_hz"])
    sub(sensor, "visualize", "false")
    sub(sensor, "topic", top["image"]["gz"])
    sub(sensor, "gz_frame_id", cam["optical_frame"])
    camera = sub(sensor, "camera", name="dashcam")
    sub(camera, "camera_info_topic", top["camera_info"]["gz"])
    sub(camera, "horizontal_fov", design["hfov"])
    image = sub(camera, "image")
    sub(image, "width", str(design["w"]))
    sub(image, "height", str(design["h"]))
    sub(image, "format", "R8G8B8")
    sub(image, "anti_aliasing", str(cam["anti_aliasing"]))
    clip = sub(camera, "clip")
    sub(clip, "near", cam["clip_m"][0])
    sub(clip, "far", cam["clip_m"][1])
    noise = sub(camera, "noise")
    sub(noise, "type", "gaussian")
    sub(noise, "mean", 0.0)
    sub(noise, "stddev", noise_sigma_255 / 255.0)

    sus = suspension(veh, gravity)
    for corner, (front, side) in CORNERS.items():
        x = (1 if front else -1) * veh["wheelbase_m"] / 2
        at = [x, side * veh["track_m"] / 2, r - cg, 0, 0, 0]
        hub = sub(model, "link", name=f"{corner}_hub")
        sub(hub, "pose", at)
        _inertial(hub, veh["hub_mass_kg"], sphere_inertia(veh["hub_mass_kg"], veh["hub_radius_m"]))
        leg = sub(
            model,
            "joint",
            name=f"{corner}_suspension",
            type="prismatic" if veh["suspension"]["enabled"] else "fixed",
        )
        sub(leg, "parent", gz["frames"]["base"])
        sub(leg, "child", f"{corner}_hub")
        if veh["suspension"]["enabled"]:
            axis = sub(leg, "axis")
            sub(axis, "xyz", [0, 0, 1])
            lim = sub(axis, "limit")
            sub(lim, "lower", -veh["suspension"]["travel_m"])
            sub(lim, "upper", veh["suspension"]["travel_m"])
            dyn = sub(axis, "dynamics")
            sub(dyn, "damping", sus["damping"])
            sub(dyn, "spring_reference", sus["reference"])
            sub(dyn, "spring_stiffness", sus["stiffness"])
        carrier = f"{corner}_hub"
        if front:
            steer = sub(model, "link", name=f"{corner}_steer")
            sub(steer, "pose", at)
            _inertial(
                steer, veh["hub_mass_kg"], sphere_inertia(veh["hub_mass_kg"], veh["hub_radius_m"])
            )
            j = sub(model, "joint", name=f"{corner}_steering", type="revolute")
            sub(j, "parent", carrier)
            sub(j, "child", f"{corner}_steer")
            axis = sub(j, "axis")
            sub(axis, "xyz", [0, 0, 1])
            lim = sub(axis, "limit")
            sub(lim, "lower", -veh["steering"]["limit_rad"])
            sub(lim, "upper", veh["steering"]["limit_rad"])
            sub(lim, "effort", veh["steering"]["effort_nm"])
            carrier = f"{corner}_steer"
        wheel = sub(model, "link", name=f"{corner}_wheel")
        sub(wheel, "pose", at)
        _inertial(wheel, wh["mass_kg"], cylinder_inertia_y(wh["mass_kg"], r, wh["width_m"]))
        vis = sub(wheel, "visual", name="tyre")
        sub(vis, "pose", [0, 0, 0, math.pi / 2, 0, 0])
        cyl = sub(sub(vis, "geometry"), "cylinder")
        sub(cyl, "radius", r)
        sub(cyl, "length", wh["width_m"])
        _colour(vis, veh["rgba_wheel"])
        col = sub(wheel, "collision", name="tyre_collision")
        geom = sub(col, "geometry")
        if wh["collision"] == "sphere":
            sub(sub(geom, "sphere"), "radius", r)
        else:
            sub(col, "pose", [0, 0, 0, math.pi / 2, 0, 0])
            cyl = sub(geom, "cylinder")
            sub(cyl, "radius", r)
            sub(cyl, "length", wh["width_m"])
        ode = sub(sub(sub(col, "surface"), "friction"), "ode")
        sub(ode, "mu", wh["mu"])
        sub(ode, "mu2", wh["mu2"])
        j = sub(model, "joint", name=f"{corner}_wheel_joint", type="revolute")
        sub(j, "parent", carrier)
        sub(j, "child", f"{corner}_wheel")
        sub(sub(j, "axis"), "xyz", [0, 1, 0])

    drv, base = veh["drive"], gz["frames"]["base"]
    jerk = drv["max_jerk_mps3"]
    limits = {} if jerk is None else {"min_jerk": -jerk, "max_jerk": jerk}
    plugin(
        model,
        "gz-sim-ackermann-steering-system",
        "gz::sim::systems::AckermannSteering",
        left_joint="rear_left_wheel_joint",
        right_joint="rear_right_wheel_joint",
        left_steering_joint="front_left_steering",
        right_steering_joint="front_right_steering",
        kingpin_width=veh["track_m"],
        steering_limit=veh["steering"]["limit_rad"],
        steer_p_gain=veh["steering"]["p_gain"],
        wheel_base=veh["wheelbase_m"],
        wheel_separation=veh["track_m"],
        wheel_radius=r,
        min_velocity=-drv["max_velocity_mps"],
        max_velocity=drv["max_velocity_mps"],
        min_acceleration=-brake_mps2,
        max_acceleration=drv["max_acceleration_mps2"],
        **limits,
        topic=top["cmd_vel"]["gz"],
        odom_topic=top["wheel_odom"]["gz"],
        tf_topic=f"{top['wheel_odom']['gz']}/tf",  # never bridged: /tf carries the true pose
        frame_id=gz["frames"]["odom"],
        child_frame_id=base,
        odom_publish_frequency=str(veh["odom_hz"]),
    )
    plugin(
        model,
        "gz-sim-odometry-publisher-system",
        "gz::sim::systems::OdometryPublisher",
        odom_frame=gz["frames"]["odom"],
        robot_base_frame=base,
        odom_publish_frequency=str(veh["odom_hz"]),
        odom_topic=top["odom"]["gz"],
        tf_topic=top["tf"]["gz"],
        dimensions="3",
    )
    plugin(
        model,
        "gz-sim-joint-state-publisher-system",
        "gz::sim::systems::JointStatePublisher",
        topic=top["joint_states"]["gz"],
        update_rate=str(veh["joint_state_hz"]),
    )
    ET.indent(sdf)
    return '<?xml version="1.0"?>\n' + ET.tostring(sdf, encoding="unicode") + "\n"
