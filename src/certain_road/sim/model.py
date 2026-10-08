"""Kinematic bicycle model for the simulated robot.

Deliberately simple: no tyre slip, no mass, no actuator lag. It exists so the
real `driving/` decision code can be exercised against repeatable geometry, not
to predict how the physical robot will handle. Anything that depends on real
dynamics — settling time, understeer, wheel slip — can only be measured on the
robot itself.

World frame: `x` forward, `y` left, `heading` in radians counter-clockwise from
+x. The robot starts at the origin facing +x.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from pathlib import Path

import yaml

from certain_road.canbus.protocol import Action, Command, Mode


@dataclass(frozen=True)
class Camera:
    """Idealised pinhole camera. No lens distortion, no calibration."""

    height_m: float
    pitch_rad: float
    hfov_rad: float
    img_w: int
    img_h: int

    @property
    def vfov_rad(self) -> float:
        return 2.0 * math.atan(math.tan(self.hfov_rad / 2.0) * self.img_h / self.img_w)


@dataclass(frozen=True)
class Robot:
    wheelbase_m: float
    length_m: float
    width_m: float
    max_speed_mps: float
    max_steer_rad: float
    camera: Camera


@dataclass(frozen=True)
class RobotState:
    x: float
    y: float
    heading: float
    speed: float


def load_robot(path: Path) -> Robot:
    raw = yaml.safe_load(Path(path).read_text())
    r, c = raw["robot"], raw["camera"]
    return Robot(
        wheelbase_m=float(r["wheelbase_m"]),
        length_m=float(r["length_m"]),
        width_m=float(r["width_m"]),
        max_speed_mps=float(r["max_speed_mps"]),
        max_steer_rad=float(r["max_steer_rad"]),
        camera=Camera(
            height_m=float(c["height_m"]),
            pitch_rad=float(c["pitch_rad"]),
            hfov_rad=float(c["hfov_rad"]),
            img_w=int(c["img_w"]),
            img_h=int(c["img_h"]),
        ),
    )


def step(state: RobotState, command: Command, dt: float, robot: Robot) -> RobotState:
    """Advance one timestep. Deterministic: same inputs always give same output.

    Day 14's measurements depend on that determinism, so it is covered by a test
    rather than assumed.
    """
    if command.action is Action.STOP:
        velocity = 0.0
    else:
        sign = -1.0 if command.action is Action.REVERSE else 1.0
        velocity = sign * command.speed * robot.max_speed_mps

    if velocity == 0.0:
        return RobotState(state.x, state.y, state.heading, 0.0)

    steer_angle = command.steer * robot.max_steer_rad
    return RobotState(
        x=state.x + velocity * math.cos(state.heading) * dt,
        y=state.y + velocity * math.sin(state.heading) * dt,
        heading=state.heading + (velocity / robot.wheelbase_m) * math.tan(steer_angle) * dt,
        speed=velocity,
    )


def command_velocity(command: Command, robot: Robot) -> tuple[float, float]:
    """`(linear_mps, yaw_rate_radps)` that `step` drives `command` at.

    These are the physical units a ROS `/cmd_vel` Twist carries (D093), so a `Command`
    can leave the planner as a Twist and arrive at the simulated vehicle unchanged.
    """
    if command.action is Action.STOP:
        return 0.0, 0.0
    sign = -1.0 if command.action is Action.REVERSE else 1.0
    velocity = sign * command.speed * robot.max_speed_mps
    yaw_rate = (velocity / robot.wheelbase_m) * math.tan(command.steer * robot.max_steer_rad)
    return velocity, yaw_rate


def command_from_velocity(linear_mps: float, yaw_rate_radps: float, robot: Robot) -> Command:
    """The inverse of `command_velocity`, up to float rounding.

    Lossy in two named ways: a Twist has no `Mode`, so every command reads back as
    AUTONOMOUS; and a STOP carries no speed or steer, which `step` ignores anyway.
    """
    if linear_mps == 0.0:
        return Command(Action.STOP, 0.0, 0.0, Mode.AUTONOMOUS)
    action = Action.FORWARD if linear_mps > 0.0 else Action.REVERSE
    speed = min(abs(linear_mps) / robot.max_speed_mps, 1.0)
    steer_angle = math.atan(yaw_rate_radps * robot.wheelbase_m / linear_mps)
    steer = max(-1.0, min(1.0, steer_angle / robot.max_steer_rad))
    return Command(action, speed, steer, Mode.AUTONOMOUS)
