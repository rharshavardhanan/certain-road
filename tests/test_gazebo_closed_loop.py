"""The Gazebo closed loop's pure parts: the car's profile and corridor, the stand-in driver's
rule, the scorer's geometry, and the launch's real-time-factor call.

No ROS, no Gazebo: certain_road_ros.lane_keep and certain_road_gz.launch_args import neither.
"""

import math
import sys

import numpy as np
import pytest
import yaml

from certain_road.core.geometry import ground_point, project
from certain_road.core.paths import repo_root
from certain_road.driving.corridor import corridor_polygon, load_corridor
from certain_road.sim.model import command_velocity, load_robot
from sim.gazebo import derive
from sim.gazebo.closed_loop import ahead, crossings, in_lane, inside_ellipse
from sim.mujoco.road import Instance, Road

sys.path.insert(0, str(repo_root() / "ros" / "certain_road_ros"))
sys.path.insert(0, str(repo_root() / "ros" / "certain_road_gz"))
from certain_road_gz import launch_args  # noqa: E402
from certain_road_ros.lane_keep import blend, heading, yaw_rate  # noqa: E402

GZ = yaml.safe_load((repo_root() / "configs/sim/gazebo.yaml").read_text())
PROJECT = yaml.safe_load((repo_root() / "configs/project.yaml").read_text())
DECISION = yaml.safe_load((repo_root() / "configs/driving/decision.yaml").read_text())
ROBOT_CORRIDOR = yaml.safe_load((repo_root() / "configs/driving/corridor.yaml").read_text())
DEMO = yaml.safe_load((repo_root() / "configs/ros/demo.yaml").read_text())
CAR = load_robot(repo_root() / "configs/sim/car.yaml")
CORRIDOR = load_corridor(repo_root() / "configs/driving/corridor_car.yaml")
S = PROJECT["sim"]
KW = {
    "f": (S["cam_w"] / 2) / math.tan(S["cam_fov_rad"] / 2),
    "cx": S["cam_w"] / 2,
    "cy": S["cam_h"] / 2,
    "cam_h": S["cam_height_m"],
    "pitch": math.radians(S["cam_pitch_deg"]),
}


def test_car_profile_cruises_at_the_design_speed_and_steers_to_the_cars_lock():
    from certain_road.canbus.protocol import Action, Command, Mode

    cruise = Command(Action.FORWARD, DECISION["manoeuvre"]["cruise_speed"], 0.0, Mode.AUTONOMOUS)
    assert command_velocity(cruise, CAR)[0] == pytest.approx(S["speed_kmh"] / 3.6, abs=1e-5)
    assert CAR.max_steer_rad == GZ["vehicle"]["steering"]["limit_rad"]
    assert CAR.wheelbase_m == GZ["vehicle"]["wheelbase_m"]
    # the Ackermann plugin reads a yaw rate back into this same steering angle
    full = Command(Action.FORWARD, 0.35, 0.7, Mode.AUTONOMOUS)
    v, w = command_velocity(full, CAR)
    assert math.atan(w * CAR.wheelbase_m / v) == pytest.approx(0.7 * CAR.max_steer_rad)
    assert (CAR.camera.img_w, CAR.camera.img_h, CAR.camera.height_m) == (1280, 720, 1.3)


def test_car_corridor_is_the_projection_of_the_cars_strip():
    c = derive.car_corridor(GZ, PROJECT, DECISION, ROBOT_CORRIDOR)
    half = c["_numbers"]["half_width_m"]
    w, h = S["cam_w"], S["cam_h"]
    poly = corridor_polygon(CORRIDOR, w, h)
    # every corner is y = +-W on the ground, at the look-ahead (top) and the near edge (bottom)
    far, near = c["_numbers"]["far_m"], ground_point(KW["cx"], h, **KW)[0]
    for (u, v), (d, side) in zip(poly, [(far, 1), (far, -1), (near, -1), (near, 1)], strict=True):
        pu, pv = project(d, side * half, **KW)
        assert (u, v) == pytest.approx((pu, pv), abs=0.6)  # 4-decimal fractions of the frame
    # straight through a pinhole: the edge at an intermediate distance lies on the polygon side
    mid = 6.0
    pu, pv = project(mid, half, **KW)
    a, b = poly[0], poly[3]  # top-left to bottom-left: the left edge is y = +W
    t = (pv - a[1]) / (b[1] - a[1])
    assert a[0] + t * (b[0] - a[0]) == pytest.approx(pu, abs=1.0)
    n = c["_numbers"]
    assert n["near_edge_m"] < n["stop_m"] <= n["decide_m"] < n["far_m"]
    assert CORRIDOR.top_y < CORRIDOR.near_proximity < CORRIDOR.imminent_proximity < 1.0


def test_car_files_are_generated_not_edited():
    from sim.gazebo import package

    stale = [p for p in package.stale() if p.startswith("configs/")]
    assert stale == [], "run: python -m sim.gazebo.package"


def test_stand_in_steers_back_and_yields_to_the_planner():
    cfg = DEMO["lane_keeper"]
    assert yaw_rate(0.5, 0.0, cfg) < 0 < yaw_rate(-0.5, 0.0, cfg)  # left of centre: turn right
    assert yaw_rate(0.0, 0.2, cfg) < 0  # heading left: turn right
    assert abs(yaw_rate(5.0, 1.0, cfg)) == cfg["max_yaw_rate"]
    planner = (2.5, 0.0)
    for state in ("normal", "warning"):
        (lin, w), steering = blend(state, planner, -0.1, cfg)
        assert steering and lin == 2.5 and w == -0.1  # the planner's speed, the stand-in's steer
    for state in ("avoid_left", "avoid_right", "stop"):
        (lin, w), steering = blend(state, (1.9, 0.35), -0.1, cfg)
        assert not steering and (lin, w) == (1.9, 0.35)  # the planner's Twist, unchanged
    assert blend("normal", (0.0, 0.0), -0.1, cfg) == ((0.0, 0.0), False)  # never steer at rest
    q = (math.cos(0.15), 0.0, 0.0, math.sin(0.15))
    assert heading(*q) == pytest.approx(0.3)


def _pothole(i, x, y, length, width, angle=0.0):
    return Instance(i, "pothole", x, y, length, width, angle, 0.5, "p", (0, 0, 0, 0))


ROAD = Road(
    "poor",
    0,
    100.0,
    3.5,
    1.75,
    (
        _pothole(0, 20.0, 1.0, 0.8, 0.6),  # in the left (driving) lane, under the right wheels
        _pothole(1, 40.0, -2.0, 0.8, 0.6),  # the other lane
        _pothole(2, 60.0, 1.75, 0.6, 0.6),  # between the wheels
    ),
)


def test_ellipse_lane_and_crossing_geometry():
    p0, p1, _ = ROAD.instances
    assert inside_ellipse([20.0, 20.39, 20.45], [1.0, 1.0, 1.0], p0).tolist() == [True, True, False]
    assert inside_ellipse([20.45], [1.0], p0, grow=0.09).tolist() == [True]
    assert in_lane(p0, (0.0, 3.5), 32) and not in_lane(p1, (0.0, 3.5), 32)
    xs = np.linspace(0, 100, 2001)
    tracks = {  # a car centred on the lane: wheels at y = 1.75 -+ 0.75
        "front_right": np.stack([xs, np.full_like(xs, 1.0)], 1),
        "front_left": np.stack([xs, np.full_like(xs, 2.5)], 1),
    }
    hit = crossings(ROAD, tracks, grow=0.09)
    assert hit == {0: ["front_right"]}  # pothole 2 sits between the wheels: straddled


def test_ahead_finds_what_the_corridor_strip_covers():
    odom = np.array([[0.0, 15.0, 1.75, 0.55, 1.0, 0.0, 0.0, 0.0, 5.0]])
    # camera 2 m ahead of base: pothole 0 is 3 m ahead, 0.75 m right: inside a 1.04 m strip
    assert ahead(ROAD, odom, 0.0, 2.0, 1.04, 12.0) == {"pothole": [0]}
    assert ahead(ROAD, odom, 0.0, 2.0, 0.3, 12.0) == {}  # a narrower strip misses it


def test_set_physics_keeps_the_step_and_retries(tmp_path):
    world = tmp_path / "world.sdf"
    world.write_text(
        "<sdf><world name='w'><physics><max_step_size>0.002</max_step_size></physics></world></sdf>"
    )
    step = launch_args.physics_step(world)
    script = launch_args.set_physics_script("w", step, 0.3, 5, 2.0)
    assert step == 0.002 and "/world/w/set_physics" in script
    assert "max_step_size: 0.002, real_time_factor: 0.3" in script and "seq 5" in script
