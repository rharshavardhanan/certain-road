"""The loop that runs on the Jetson: frames in, CAN frames out.

    FrameSource -> detector -> build_perception -> next_state -> Command -> Transport

Every module in that chain is the same one the simulator exercises. The only
difference is where detections come from — a real detector on real footage here,
a pinhole projection of world geometry there — which is what makes a passing
scenario evidence about this code rather than about a parallel implementation.

The detector is injected as a plain callable rather than constructed here. That
keeps the loop testable with a stub on a laptop with no weights, no GPU and no
bus, and it is why this file can be trusted before it ever reaches the Jetson.
"""

from __future__ import annotations

from collections.abc import Callable, Iterator
from dataclasses import dataclass

from certain_road.artifacts.schema import Detection
from certain_road.canbus.protocol import Command
from certain_road.canbus.transport import Transport
from certain_road.driving.confirm import Confirmer
from certain_road.driving.controller import command_for
from certain_road.driving.corridor import Corridor
from certain_road.driving.decision import DriveState, Policy, next_state
from certain_road.driving.perceive import build_perception
from certain_road.perception.source import Frame, FrameSource

Detector = Callable[[Frame], list[Detection]]


@dataclass(frozen=True)
class Step:
    """One frame's worth of what happened. The survey pipeline reads these."""

    frame_id: str
    timestamp_s: float
    detections: list[Detection]  # everything above the record threshold
    governing: Detection | None  # the hazard that drove the decision, if any
    drive_state: DriveState
    command: Command


def run(
    source: FrameSource,
    detector: Detector,
    corridor: Corridor,
    policy: Policy,
    transport: Transport,
    *,
    escape_lanes: float,
) -> Iterator[Step]:
    """Drive the loop, yielding one `Step` per frame.

    A generator on purpose: the caller decides what to do with each step —
    record it, render it, count it — without this loop knowing about any of that.
    """
    confirmer = Confirmer(policy.required, policy.window)
    drive_state = DriveState.NORMAL

    for frame in source.frames():
        detected = detector(frame)

        # Two thresholds, one detector (D051). The weaker bar records evidence for
        # the survey; only the stronger bar may steer the vehicle.
        recorded = [d for d in detected if d.score >= policy.record_min_score]
        actionable = [d for d in recorded if d.score >= policy.intervene_min_score]

        perception, governing = build_perception(
            actionable, corridor, confirmer, escape_lanes=escape_lanes
        )
        drive_state = next_state(drive_state, perception, policy)
        command = command_for(drive_state, policy)
        transport.send(command)

        yield Step(
            frame_id=frame.frame_id,
            timestamp_s=frame.timestamp_s,
            detections=recorded,
            governing=governing,
            drive_state=drive_state,
            command=command,
        )
