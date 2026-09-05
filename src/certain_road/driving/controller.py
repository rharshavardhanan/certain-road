"""Turn a drive state into a wire `Command`.

Kept separate from the state machine so the policy ("what should happen") and the
actuation ("how fast, how hard") can be tuned independently — and so the state
machine stays testable without any notion of speed or steering.
"""

from __future__ import annotations

from certain_road.canbus.protocol import Action, Command, Mode
from certain_road.driving.decision import DriveState, Policy

# model.py: positive steer increases heading, i.e. turns left.
_LEFT = +1.0
_RIGHT = -1.0


def command_for(state: DriveState, policy: Policy) -> Command:
    if state is DriveState.STOP:
        return Command(Action.STOP, 0.0, 0.0, Mode.AUTONOMOUS)
    if state is DriveState.NORMAL:
        return Command(Action.FORWARD, policy.cruise_speed, 0.0, Mode.AUTONOMOUS)
    if state is DriveState.WARNING:
        return Command(Action.FORWARD, policy.caution_speed, 0.0, Mode.AUTONOMOUS)
    steer = _LEFT if state is DriveState.AVOID_LEFT else _RIGHT
    return Command(Action.FORWARD, policy.avoid_speed, steer * policy.avoid_steer, Mode.AUTONOMOUS)
