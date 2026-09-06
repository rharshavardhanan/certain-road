"""The drive state machine.

Pure logic over a `Perception` snapshot: no camera, no robot, no I/O. That is
deliberate — decisions must be provably correct before they are wired to
actuators, and debugging a state bug while the robot is moving is both slow and
dangerous.

**Ordering rule that matters:** failsafes are evaluated first and outrank
everything, including a clear road. A stale or unhealthy perception input means
the machine stops, whatever it last believed about the world.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path

import yaml

from certain_road.driving.corridor import Urgency


class DriveState(StrEnum):
    NORMAL = "normal"
    WARNING = "warning"
    AVOID_LEFT = "avoid_left"
    AVOID_RIGHT = "avoid_right"
    STOP = "stop"


@dataclass(frozen=True)
class Hazard:
    """A confirmed hazard, already through temporal confirmation."""

    lateral_offset: float  # -1 far left .. +1 far right, relative to the corridor
    urgency: Urgency
    score: float


@dataclass(frozen=True)
class Perception:
    """One frame's view of the world, as the state machine sees it."""

    hazard: Hazard | None
    left_blocked: bool
    right_blocked: bool
    frame_age: int
    healthy: bool


@dataclass(frozen=True)
class Policy:
    required: int
    window: int
    intervene_min_score: float
    record_min_score: float
    max_frame_age: int
    cruise_speed: float
    caution_speed: float
    avoid_speed: float
    avoid_steer: float
    preferred_side: str


def load_policy(path: Path) -> Policy:
    raw = yaml.safe_load(Path(path).read_text())
    c, s, f, m = raw["confirmation"], raw["confidence"], raw["staleness"], raw["manoeuvre"]
    if m["preferred_side"] not in {"left", "right"}:
        raise ValueError(f"preferred_side must be 'left' or 'right', got {m['preferred_side']!r}")
    return Policy(
        required=int(c["required"]),
        window=int(c["window"]),
        intervene_min_score=float(s["intervene_min_score"]),
        record_min_score=float(s["record_min_score"]),
        max_frame_age=int(f["max_frame_age"]),
        cruise_speed=float(m["cruise_speed"]),
        caution_speed=float(m["caution_speed"]),
        avoid_speed=float(m["avoid_speed"]),
        avoid_steer=float(m["avoid_steer"]),
        preferred_side=str(m["preferred_side"]),
    )


def next_state(current: DriveState, perception: Perception, policy: Policy) -> DriveState:
    """Compute the next state. Deterministic and side-effect free."""
    # 1. Failsafes first. These outrank every other consideration.
    if not perception.healthy or perception.frame_age > policy.max_frame_age:
        return DriveState.STOP

    haz = perception.hazard

    # 2. No hazard, or one too weak to justify steering: carry on.
    #    A sub-threshold detection is still recorded for the survey — that
    #    happens in the survey pipeline, not here.
    if haz is None or haz.score < policy.intervene_min_score:
        return DriveState.NORMAL

    # 3. Distant hazard: slow and keep watching, do not steer yet.
    if haz.urgency is Urgency.FAR:
        return DriveState.WARNING

    # 4. Hysteresis: a manoeuvre already under way is not reconsidered while it is
    #    still viable. Without this the machine re-derives a side every frame and
    #    flip-flops on noise around the centreline — which on a real vehicle wastes
    #    the manoeuvre and looks like indecision.
    #
    #    The commitment is released only by something that genuinely invalidates
    #    it: the hazard clearing (handled above, which returns NORMAL), or the
    #    committed side becoming blocked. Reacting to a newly-visible blocker is
    #    not oscillation — it is the correct response to new information.
    if current is DriveState.AVOID_LEFT and not perception.left_blocked:
        return DriveState.AVOID_LEFT
    if current is DriveState.AVOID_RIGHT and not perception.right_blocked:
        return DriveState.AVOID_RIGHT

    # 5. Choose an escape side, or stop.
    #    Steer AWAY from the hazard: one on the left means going right.
    wants_right = haz.lateral_offset < 0
    wants_left = haz.lateral_offset > 0
    if not wants_right and not wants_left:  # dead centre
        wants_right = policy.preferred_side == "right"
        wants_left = not wants_right

    if wants_right and not perception.right_blocked:
        return DriveState.AVOID_RIGHT
    if wants_left and not perception.left_blocked:
        return DriveState.AVOID_LEFT

    # Preferred side is blocked — try the other one.
    if not perception.right_blocked:
        return DriveState.AVOID_RIGHT
    if not perception.left_blocked:
        return DriveState.AVOID_LEFT

    # Both blocked. Stopping is the only safe action; guessing a side is not.
    return DriveState.STOP
