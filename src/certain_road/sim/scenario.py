"""Repeatable trial scenarios.

Today the robot drives a fixed command sequence — enough to prove the kinematics,
the projection and the render. Closing the loop, so the state machine steers the
robot around the hazard, is Day 6.

Scenarios are the unit Day 8 and Day 14 measure over: deterministic, headless, and
re-runnable after any code change, which is what staging obstacles physically can
never be.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from certain_road.canbus.protocol import Action, Command, Mode
from certain_road.sim.model import RobotState


@dataclass(frozen=True)
class Pothole:
    x: float
    y: float
    radius: float = 0.15


@dataclass(frozen=True)
class Scenario:
    name: str
    potholes: list[Pothole]
    start: RobotState
    commands: list[Command]
    dt: float = 0.1
    description: str = ""


def _straight(n: int, speed: float = 1.0) -> list[Command]:
    return [Command(Action.FORWARD, speed, 0.0, Mode.AUTONOMOUS) for _ in range(n)]


SCENARIOS: dict[str, Scenario] = {
    "centre": Scenario(
        name="centre",
        potholes=[Pothole(x=1.5, y=0.0, radius=0.18)],
        start=RobotState(0.0, 0.0, 0.0, 0.0),
        commands=_straight(40),
        description="One pothole dead ahead. The robot drives straight at it on fixed "
        "commands; the corridor test should flip to in-path as it closes.",
    ),
    "offset": Scenario(
        name="offset",
        potholes=[Pothole(x=1.5, y=0.45, radius=0.18)],
        start=RobotState(0.0, 0.0, 0.0, 0.0),
        commands=_straight(40),
        description="Pothole to the left of the driving line — should be seen but "
        "judged out of path, so no manoeuvre is warranted.",
    ),
}


@dataclass
class Trace:
    """What one scenario run produced, frame by frame."""

    states: list[RobotState] = field(default_factory=list)
    in_path: list[bool] = field(default_factory=list)
    urgency: list[str] = field(default_factory=list)
    detections: list[object] = field(default_factory=list)  # Detection | None per frame
