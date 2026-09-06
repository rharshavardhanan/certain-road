"""Closed-loop scenario runner: perception → confirmation → decision → actuation.

This is the composition root. `sim/` may import `driving/` and `canbus/` — wiring
them together is its job — but never `survey/` or `dashboard/` (D049, enforced).

Every module in the chain is the **real** one. The only synthetic parts are the
projection (world → image) and the actuation (command → motion). That is what
makes a passing scenario evidence about the shipping code rather than about a
parallel implementation.
"""

from __future__ import annotations

import yaml

from certain_road.core.paths import repo_root
from certain_road.driving.confirm import Confirmer
from certain_road.driving.controller import command_for
from certain_road.driving.corridor import Corridor
from certain_road.driving.decision import DriveState, Policy, next_state
from certain_road.driving.perceive import build_perception
from certain_road.sim.model import Robot, step
from certain_road.sim.project import project_pothole
from certain_road.sim.scenario import Scenario, Trace


def _escape_lanes() -> float:
    raw = yaml.safe_load((repo_root() / "configs" / "driving" / "corridor.yaml").read_text())
    return float(raw["escape_lanes"])


def run_scenario(
    scenario: Scenario,
    robot: Robot,
    corridor: Corridor,
    policy: Policy,
    *,
    frames: int | None = None,
) -> Trace:
    """Drive the scenario under closed-loop control."""
    escape_lanes = _escape_lanes()

    trace = Trace()
    state = scenario.start
    drive_state = DriveState.NORMAL
    confirmer = Confirmer(policy.required, policy.window)
    n = frames if frames is not None else len(scenario.commands)

    for _ in range(n):
        dets = [
            d
            for p in scenario.potholes
            if (d := project_pothole(p.x, p.y, p.radius, state, robot.camera)) is not None
        ]

        perception, nearest = build_perception(dets, corridor, confirmer, escape_lanes=escape_lanes)
        hazard = perception.hazard

        drive_state = next_state(drive_state, perception, policy)
        command = command_for(drive_state, policy)
        state = step(state, command, scenario.dt, robot)

        trace.states.append(state)
        trace.detections.append(nearest)
        trace.in_path.append(nearest is not None)
        trace.urgency.append(str(hazard.urgency) if hazard else "none")
        trace.drive_state.append(str(drive_state))
        trace.commands.append(command)

    return trace
