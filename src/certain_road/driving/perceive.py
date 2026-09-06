"""Turn a frame's detections into a `Perception` the state machine can judge.

**Why this is its own module.** The simulator and the on-device runtime both need
exactly this step, and it is the part with the subtle rules — which hazard governs,
what counts as blocking an escape, when confirmation applies. Duplicating it would
mean the simulator could pass while the runtime failed, which would make every
simulated result worthless as evidence about the shipping code.

Pure: no I/O, no camera, no bus.
"""

from __future__ import annotations

from certain_road.artifacts.schema import Detection
from certain_road.driving.confirm import Confirmer
from certain_road.driving.corridor import (
    Corridor,
    Zone,
    in_path,
    lateral_offset,
    lateral_zone,
    urgency,
)
from certain_road.driving.decision import Hazard, Perception


def build_perception(
    detections: list[Detection],
    corridor: Corridor,
    confirmer: Confirmer,
    *,
    escape_lanes: float,
    frame_age: int = 0,
    healthy: bool = True,
) -> tuple[Perception, Detection | None]:
    """Judge one frame. Returns the perception and the governing detection, if any.

    The governing hazard is the nearest one on the driving line — lower in the
    frame is nearer (see `corridor.proximity`).
    """
    ahead = [d for d in detections if in_path(d, corridor, min_overlap=corridor.min_overlap)]
    nearest = max(ahead, key=lambda d: d.y2) if ahead else None

    confirmed = confirmer.update(nearest is not None)

    hazard = None
    if confirmed and nearest is not None:
        hazard = Hazard(
            lateral_offset=lateral_offset(nearest, corridor),
            urgency=urgency(nearest, corridor),
            score=nearest.score,
        )

    # The governing hazard is excluded from escape blocking. Once the vehicle is
    # swerving, that hazard drifts out of PATH into the escape zone on the side
    # being steered away from; counting it would let the vehicle block its own
    # manoeuvre. The question is whether something ELSE occupies the lane.
    others = [d for d in detections if d is not nearest]
    zones = [lateral_zone(d, corridor, escape_lanes=escape_lanes) for d in others]

    return (
        Perception(
            hazard=hazard,
            left_blocked=Zone.LEFT in zones,
            right_blocked=Zone.RIGHT in zones,
            frame_age=frame_age,
            healthy=healthy,
        ),
        nearest,
    )
