"""Run a scenario: kinematics, projection, and the REAL corridor decision.

This is the composition root. `sim/` may import `driving/` and `canbus/` — wiring
them is its job — but never `survey/` or `dashboard/` (D049, enforced by
import-linter).
"""

from __future__ import annotations

from certain_road.driving.corridor import Corridor, in_path, urgency
from certain_road.sim.model import Robot, step
from certain_road.sim.project import project_pothole
from certain_road.sim.scenario import Scenario, Trace


def run_scenario(scenario: Scenario, robot: Robot, corridor: Corridor) -> Trace:
    """Drive the fixed command sequence, judging each frame with the real corridor code.

    Only the nearest visible pothole is judged per frame — the state machine (Day 6)
    is what will reason about several at once.
    """
    trace = Trace()
    state = scenario.start

    for command in scenario.commands:
        state = step(state, command, scenario.dt, robot)

        best = None
        for p in scenario.potholes:
            det = project_pothole(p.x, p.y, p.radius, state, robot.camera)
            if det is not None and (best is None or det.y2 > best.y2):
                best = det  # lower in frame == nearer

        if best is None:
            trace.in_path.append(False)
            trace.urgency.append("none")
        else:
            trace.in_path.append(in_path(best, corridor, min_overlap=corridor.min_overlap))
            trace.urgency.append(str(urgency(best, corridor)))

        trace.states.append(state)
        trace.detections.append(best)

    return trace
