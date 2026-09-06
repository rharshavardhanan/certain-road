"""The on-device loop, run end to end on a laptop.

No weights, no GPU, no camera, no bus: the detector is a stub and the transport is
NullTransport. Everything between them is the code that will run on the Jetson.
"""

import numpy as np
import pytest

from certain_road.artifacts.schema import Detection
from certain_road.canbus.protocol import Action
from certain_road.canbus.transport import NullTransport
from certain_road.core.paths import repo_root
from certain_road.driving.corridor import load_corridor
from certain_road.driving.decision import DriveState, load_policy
from certain_road.perception.source import Frame, FrameSource
from certain_road.runtime.pipeline import run

CORRIDOR = load_corridor(repo_root() / "configs" / "driving" / "corridor.yaml")
POLICY = load_policy(repo_root() / "configs" / "driving" / "decision.yaml")
W = H = 640


class FakeSource(FrameSource):
    def __init__(self, n: int) -> None:
        self.n = n

    def frames(self):
        for i in range(self.n):
            yield Frame(f"f{i:04d}", np.zeros((H, W, 3), dtype=np.uint8), i * 0.1)


def centred_pothole(score: float = 0.9) -> Detection:
    """Low and centred: inside the corridor, near enough to act on."""
    return Detection("pothole", score, 290.0, 560.0, 350.0, 620.0, W, H)


def edge_pothole(score: float = 0.9) -> Detection:
    return Detection("pothole", score, 0.0, 560.0, 60.0, 620.0, W, H)


def run_all(detector, frames=12, transport=None):
    transport = transport or NullTransport()
    steps = list(run(FakeSource(frames), detector, CORRIDOR, POLICY, transport, escape_lanes=5.0))
    return steps, transport


def test_empty_road_never_leaves_normal():
    steps, transport = run_all(lambda f: [])
    assert {s.drive_state for s in steps} == {DriveState.NORMAL}
    assert all(c.action is Action.FORWARD for c in transport.sent)


def test_a_command_is_sent_for_every_frame():
    """The vehicle must never be left without a current command."""
    steps, transport = run_all(lambda f: [], frames=9)
    assert len(transport.sent) == 9 == len(steps)


def test_persistent_centred_hazard_triggers_a_manoeuvre():
    steps, _ = run_all(lambda f: [centred_pothole()])
    assert any(s.drive_state in (DriveState.AVOID_LEFT, DriveState.AVOID_RIGHT) for s in steps)


def test_single_frame_false_positive_never_steers():
    """N-of-M confirmation, exercised through the whole loop rather than alone."""

    def flaky(frame):
        return [centred_pothole()] if frame.frame_id == "f0003" else []

    steps, _ = run_all(flaky)
    assert all(s.drive_state is DriveState.NORMAL for s in steps)


def test_low_confidence_hazard_is_recorded_but_never_steers():
    """The two-threshold rule: evidence for the survey, not grounds to steer."""
    weak = 0.25
    assert POLICY.record_min_score < weak < POLICY.intervene_min_score

    steps, _ = run_all(lambda f: [centred_pothole(score=weak)])
    assert all(s.drive_state is DriveState.NORMAL for s in steps)
    assert all(len(s.detections) == 1 for s in steps), "still recorded for the survey"


def test_detections_below_the_record_threshold_are_dropped_entirely():
    steps, _ = run_all(lambda f: [centred_pothole(score=0.02)])
    assert all(s.detections == [] for s in steps)


def test_hazard_outside_the_corridor_does_not_steer():
    steps, _ = run_all(lambda f: [edge_pothole()])
    assert all(s.drive_state is DriveState.NORMAL for s in steps)
    assert all(len(s.detections) == 1 for s in steps), "seen, just not in the way"


def test_steps_carry_the_governing_hazard_for_the_survey():
    steps, _ = run_all(lambda f: [centred_pothole()])
    assert any(s.governing is not None for s in steps)


def test_frame_identity_is_preserved_end_to_end():
    steps, _ = run_all(lambda f: [], frames=4)
    assert [s.frame_id for s in steps] == ["f0000", "f0001", "f0002", "f0003"]


@pytest.mark.parametrize("n", [1, 5, 30])
def test_loop_is_deterministic(n):
    a, _ = run_all(lambda f: [centred_pothole()], frames=n)
    b, _ = run_all(lambda f: [centred_pothole()], frames=n)
    assert [s.drive_state for s in a] == [s.drive_state for s in b]
