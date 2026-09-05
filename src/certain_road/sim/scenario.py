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
    expect: str = ""  # the DriveState this run must reach; asserted in tests


def _straight(n: int, speed: float = 1.0) -> list[Command]:
    return [Command(Action.FORWARD, speed, 0.0, Mode.AUTONOMOUS) for _ in range(n)]


def _scenario(name: str, potholes: list[Pothole], expect: str, description: str) -> Scenario:
    return Scenario(
        name=name,
        potholes=potholes,
        start=RobotState(0.0, 0.0, 0.0, 0.0),
        commands=_straight(60),
        description=description,
        expect=expect,
    )


# The trial matrix. This is the unit Day 8 and Day 14 measure over: deterministic,
# headless, and re-runnable after any change — which staging obstacles physically
# can never be.
#
# `expect` is the state the run MUST reach at some point. It is asserted in the
# test suite, so a regression in the state machine breaks the build rather than
# being noticed on the floor.
SCENARIOS: dict[str, Scenario] = {
    "clear": _scenario(
        "clear",
        [],
        "normal",
        "Empty road. Must never leave NORMAL — a false manoeuvre here is as bad as a missed one.",
    ),
    "centre": _scenario(
        "centre",
        [Pothole(1.5, 0.0)],
        "avoid_right",
        "Pothole dead ahead, both sides clear. Uses the configured tie-break.",
    ),
    "left": _scenario(
        "left",
        [Pothole(1.5, 0.18)],
        "avoid_right",
        "Pothole left of the driving line: steer away from it, to the right.",
    ),
    "right": _scenario(
        "right",
        [Pothole(1.5, -0.18)],
        "avoid_left",
        "Pothole right of the driving line: steer left.",
    ),
    "multiple": _scenario(
        "multiple",
        [Pothole(1.2, 0.10), Pothole(2.0, -0.12), Pothole(2.8, 0.05)],
        "avoid_right",
        "Three hazards in sequence. The nearest one governs.",
    ),
    "blocked_left": _scenario(
        "blocked_left",
        [Pothole(1.5, -0.15), Pothole(1.5, 0.45)],
        "avoid_right",
        "Hazard on the driving line plus one blocking the LEFT escape: the "
        "machine must take the right even though the hazard sits right of centre. "
        "Blocker at 0.45 m lateral, not 0.75 m — at the decision distance the "
        "camera only sees +/-0.64 m, so a wider placement is invisible.",
    ),
    "blocked_right": _scenario(
        "blocked_right",
        [Pothole(1.5, 0.15), Pothole(1.5, -0.45)],
        "avoid_left",
        "Mirror of blocked_left.",
    ),
    "blocked_both": _scenario(
        "blocked_both",
        [Pothole(1.5, 0.0), Pothole(1.5, 0.45), Pothole(1.5, -0.45)],
        "stop",
        "Hazard ahead, both escapes blocked. Must STOP — never guess a side.",
    ),
}


@dataclass
class Trace:
    """What one scenario run produced, frame by frame."""

    states: list[RobotState] = field(default_factory=list)
    in_path: list[bool] = field(default_factory=list)
    urgency: list[str] = field(default_factory=list)
    detections: list[object] = field(default_factory=list)  # Detection | None per frame
    drive_state: list[str] = field(default_factory=list)
    commands: list[object] = field(default_factory=list)

    @property
    def states_seen(self) -> set[str]:
        return set(self.drive_state)
