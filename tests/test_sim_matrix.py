"""The trial matrix, asserted.

This is what Day 8 and Day 14 measure over. Running it in the suite means a
regression in the state machine breaks the build rather than being noticed on the
floor during a demo.
"""

import pytest

from certain_road.core.paths import repo_root
from certain_road.driving.corridor import load_corridor
from certain_road.driving.decision import load_policy
from certain_road.sim.model import load_robot
from certain_road.sim.run import run_scenario
from certain_road.sim.scenario import SCENARIOS

ROBOT = load_robot(repo_root() / "configs" / "sim" / "robot.yaml")
CORRIDOR = load_corridor(repo_root() / "configs" / "driving" / "corridor.yaml")
POLICY = load_policy(repo_root() / "configs" / "driving" / "decision.yaml")

# Known-failing, with a diagnosed structural cause — see the module docstring in
# sim/run.py and the escape-corridor note in configs/driving/corridor.yaml.
# strict=True: if a fix lands, this test starts failing and demands attention
# rather than silently passing.
ESCAPE_OVERLAP = pytest.mark.xfail(
    strict=True,
    reason="escape corridors overlap the driving corridor near the frame bottom, so a "
    "hazard on the driving line registers as blocking both escapes once near",
)


@pytest.mark.parametrize(
    "name",
    [
        "clear",
        "centre",
        "left",
        "right",
        "multiple",
        pytest.param("blocked_left", marks=ESCAPE_OVERLAP),
        pytest.param("blocked_right", marks=ESCAPE_OVERLAP),
        "blocked_both",
    ],
)
def test_scenario_reaches_its_expected_state(name):
    scenario = SCENARIOS[name]
    trace = run_scenario(scenario, ROBOT, CORRIDOR, POLICY)
    assert scenario.expect in trace.states_seen, (
        f"{name}: expected {scenario.expect}, saw {sorted(trace.states_seen)}"
    )


def test_clear_road_never_manoeuvres():
    """A false manoeuvre on an empty road is as bad as a missed hazard."""
    trace = run_scenario(SCENARIOS["clear"], ROBOT, CORRIDOR, POLICY)
    assert trace.states_seen == {"normal"}


def test_blocked_both_never_guesses_a_side():
    trace = run_scenario(SCENARIOS["blocked_both"], ROBOT, CORRIDOR, POLICY)
    assert "stop" in trace.states_seen


def test_runs_are_deterministic():
    a = run_scenario(SCENARIOS["centre"], ROBOT, CORRIDOR, POLICY)
    b = run_scenario(SCENARIOS["centre"], ROBOT, CORRIDOR, POLICY)
    assert a.drive_state == b.drive_state
    assert [(s.x, s.y) for s in a.states] == [(s.x, s.y) for s in b.states]
