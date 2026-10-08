"""Kinematics, projection, and the integration that proves the simulator
exercises the real driving code rather than paralleling it."""

import math

import pytest

from certain_road.canbus.protocol import Action, Command, Mode
from certain_road.core.paths import repo_root
from certain_road.driving.corridor import in_path, load_corridor
from certain_road.sim.model import (
    RobotState,
    command_from_velocity,
    command_velocity,
    load_robot,
    step,
)
from certain_road.sim.project import project_pothole

ROBOT = load_robot(repo_root() / "configs" / "sim" / "robot.yaml")
CORRIDOR = load_corridor(repo_root() / "configs" / "driving" / "corridor.yaml")
DT = 0.1


def fwd(steer: float = 0.0, speed: float = 0.5) -> Command:
    return Command(action=Action.FORWARD, speed=speed, steer=steer, mode=Mode.AUTONOMOUS)


def test_zero_steer_drives_straight():
    s = RobotState(x=0.0, y=0.0, heading=0.0, speed=0.0)
    for _ in range(20):
        s = step(s, fwd(steer=0.0), DT, ROBOT)
    assert s.heading == pytest.approx(0.0, abs=1e-12)
    assert s.x > 0.0
    assert s.y == pytest.approx(0.0, abs=1e-12)


def test_positive_steer_turns_left_negative_turns_right():
    start = RobotState(0.0, 0.0, 0.0, 0.0)
    left = start
    right = start
    for _ in range(10):
        left = step(left, fwd(steer=+1.0), DT, ROBOT)
        right = step(right, fwd(steer=-1.0), DT, ROBOT)
    assert left.heading > 0.0
    assert right.heading < 0.0


def test_zero_speed_never_moves():
    s = RobotState(1.0, 2.0, 0.3, 0.0)
    for _ in range(10):
        s = step(s, Command(Action.FORWARD, 0.0, 1.0, Mode.AUTONOMOUS), DT, ROBOT)
    assert (s.x, s.y, s.heading) == (1.0, 2.0, 0.3)


def test_stop_action_halts_regardless_of_speed_field():
    s = RobotState(0.0, 0.0, 0.0, 0.0)
    s2 = step(s, Command(Action.STOP, 1.0, 0.0, Mode.AUTONOMOUS), DT, ROBOT)
    assert (s2.x, s2.y) == (0.0, 0.0)


def test_trajectory_is_deterministic():
    """Day 14's measurements depend on this. Not an assumption — a test."""
    cmds = [fwd(steer=math.sin(i / 3)) for i in range(30)]

    def run():
        s = RobotState(0.0, 0.0, 0.0, 0.0)
        out = []
        for c in cmds:
            s = step(s, c, DT, ROBOT)
            out.append((s.x, s.y, s.heading))
        return out

    assert run() == run()


def test_pothole_ahead_projects_near_horizontal_centre():
    s = RobotState(0.0, 0.0, 0.0, 0.0)
    det = project_pothole(world_x=2.0, world_y=0.0, radius=0.15, state=s, camera=ROBOT.camera)
    assert det is not None
    centre_u = (det.x1 + det.x2) / 2
    assert centre_u == pytest.approx(ROBOT.camera.img_w / 2, abs=2.0)


def test_further_pothole_projects_higher_in_frame():
    """Perspective: distant ground points sit nearer the horizon, so smaller y2."""
    s = RobotState(0.0, 0.0, 0.0, 0.0)
    near = project_pothole(1.0, 0.0, 0.15, s, ROBOT.camera)
    far = project_pothole(4.0, 0.0, 0.15, s, ROBOT.camera)
    assert near is not None and far is not None
    assert far.y2 < near.y2


def test_pothole_behind_camera_is_not_visible():
    s = RobotState(0.0, 0.0, 0.0, 0.0)
    assert project_pothole(-2.0, 0.0, 0.15, s, ROBOT.camera) is None


def test_pothole_far_to_the_side_leaves_the_frame():
    s = RobotState(0.0, 0.0, 0.0, 0.0)
    assert project_pothole(1.0, 20.0, 0.15, s, ROBOT.camera) is None


def test_projected_pothole_ahead_is_in_path():
    """The integration that matters: simulated geometry -> REAL corridor code.

    If this fails the simulator is decorative — it would not be exercising
    driving/corridor.py at all.
    """
    s = RobotState(0.0, 0.0, 0.0, 0.0)
    # 0.6 m: comfortably inside the corridor's ~0.93 m look-ahead at the
    # current camera pitch. See docs — the look-ahead limit is a real
    # constraint to revisit once the camera is physically mounted.
    det = project_pothole(0.6, 0.0, 0.20, s, ROBOT.camera)
    assert det is not None
    assert in_path(det, CORRIDOR, min_overlap=CORRIDOR.min_overlap) is True


def test_projected_pothole_far_to_one_side_is_not_in_path():
    s = RobotState(0.0, 0.0, 0.0, 0.0)
    det = project_pothole(0.6, 0.9, 0.20, s, ROBOT.camera)
    if det is not None:  # may leave frame entirely, which also satisfies "not in path"
        assert in_path(det, CORRIDOR, min_overlap=CORRIDOR.min_overlap) is False


# ---- Twist units (D093): a Command crosses ROS as (m/s, rad/s) and must arrive intact --


@pytest.mark.parametrize(
    "command",
    [
        fwd(steer=0.0, speed=1.0),
        fwd(steer=0.7, speed=0.35),
        fwd(steer=-0.7, speed=0.35),
        fwd(steer=-1.0, speed=1.0),
        Command(Action.REVERSE, 0.5, 0.3, Mode.AUTONOMOUS),
    ],
)
def test_velocity_round_trip_drives_identically(command):
    v, w = command_velocity(command, ROBOT)
    back = command_from_velocity(v, w, ROBOT)
    assert back.action is command.action
    assert back.speed == pytest.approx(command.speed, abs=1e-12)
    assert back.steer == pytest.approx(command.steer, abs=1e-12)
    s = RobotState(0.2, -0.1, 0.3, 0.0)
    a, b = step(s, command, DT, ROBOT), step(s, back, DT, ROBOT)
    assert (a.x, a.y, a.heading) == pytest.approx((b.x, b.y, b.heading), abs=1e-12)


def test_stop_round_trips_to_stop():
    v, w = command_velocity(Command(Action.STOP, 0.0, 0.0, Mode.AUTONOMOUS), ROBOT)
    assert (v, w) == (0.0, 0.0)
    assert command_from_velocity(v, w, ROBOT).action is Action.STOP


def test_yaw_rate_matches_the_heading_change_step_applies():
    command = fwd(steer=0.5, speed=0.8)
    _, w = command_velocity(command, ROBOT)
    s = step(RobotState(0.0, 0.0, 0.0, 0.0), command, DT, ROBOT)
    assert s.heading == pytest.approx(w * DT, abs=1e-12)


def test_out_of_range_twist_is_clamped_not_rejected():
    """A Twist from outside the planner must not crash the vehicle with a ValueError."""
    c = command_from_velocity(ROBOT.max_speed_mps * 2, 50.0, ROBOT)
    assert c.speed == 1.0 and c.steer == 1.0
