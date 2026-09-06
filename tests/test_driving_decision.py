"""The drive decision layer: temporal confirmation, confidence gating, and the
state machine.

These run with no hardware and no camera. That is deliberate — decisions must be
provably right before they are allowed to move actuators.
"""

import pytest

from certain_road.canbus.protocol import Action
from certain_road.core.paths import repo_root
from certain_road.driving.confirm import Confirmer
from certain_road.driving.controller import command_for
from certain_road.driving.corridor import Urgency
from certain_road.driving.decision import (
    DriveState,
    Hazard,
    Perception,
    load_policy,
    next_state,
)

POLICY = load_policy(repo_root() / "configs" / "driving" / "decision.yaml")


def hazard(*, offset: float = 0.0, urgency: Urgency = Urgency.NEAR, score: float = 0.9) -> Hazard:
    return Hazard(lateral_offset=offset, urgency=urgency, score=score)


def perception(
    *,
    haz: Hazard | None = None,
    left_blocked: bool = False,
    right_blocked: bool = False,
    frame_age: int = 0,
    healthy: bool = True,
) -> Perception:
    return Perception(
        hazard=haz,
        left_blocked=left_blocked,
        right_blocked=right_blocked,
        frame_age=frame_age,
        healthy=healthy,
    )


# ---------------------------------------------------------------- confirmation


def test_single_frame_detection_never_confirms():
    """The behaviour that stops the robot twitching at shadows."""
    c = Confirmer(required=3, window=5)
    assert c.update(True) is False
    assert c.update(False) is False
    assert c.update(False) is False


def test_three_of_five_confirms():
    c = Confirmer(required=3, window=5)
    assert c.update(True) is False
    assert c.update(True) is False
    assert c.update(True) is True


def test_confirmation_decays_out_of_the_window():
    c = Confirmer(required=3, window=5)
    for _ in range(3):
        c.update(True)
    for _ in range(5):
        c.update(False)
    assert c.confirmed is False


def test_intermittent_detection_still_confirms_within_window():
    c = Confirmer(required=3, window=5)
    for present in (True, False, True, False, True):
        result = c.update(present)
    assert result is True


# ------------------------------------------------------------ confidence gate


def test_low_confidence_hazard_does_not_trigger_a_manoeuvre():
    p = perception(haz=hazard(score=0.2, urgency=Urgency.IMMINENT))
    assert next_state(DriveState.NORMAL, p, POLICY) is DriveState.NORMAL


def test_low_confidence_hazard_is_still_recordable():
    """Below the intervention threshold but above the record threshold."""
    assert POLICY.record_min_score < 0.2 < POLICY.intervene_min_score


# ------------------------------------------------------------- state machine


def test_no_hazard_is_normal():
    assert next_state(DriveState.NORMAL, perception(), POLICY) is DriveState.NORMAL


def test_far_hazard_warns_but_does_not_steer():
    p = perception(haz=hazard(urgency=Urgency.FAR))
    assert next_state(DriveState.NORMAL, p, POLICY) is DriveState.WARNING


def test_hazard_left_of_centre_steers_right():
    p = perception(haz=hazard(offset=-0.5, urgency=Urgency.NEAR))
    assert next_state(DriveState.WARNING, p, POLICY) is DriveState.AVOID_RIGHT


def test_hazard_right_of_centre_steers_left():
    p = perception(haz=hazard(offset=+0.5, urgency=Urgency.NEAR))
    assert next_state(DriveState.WARNING, p, POLICY) is DriveState.AVOID_LEFT


def test_escape_side_blocked_forces_the_other_side():
    p = perception(haz=hazard(offset=-0.5, urgency=Urgency.NEAR), right_blocked=True)
    assert next_state(DriveState.WARNING, p, POLICY) is DriveState.AVOID_LEFT


def test_both_sides_blocked_stops_and_never_guesses():
    """The rule the sprint plan calls out explicitly."""
    p = perception(
        haz=hazard(offset=0.0, urgency=Urgency.IMMINENT),
        left_blocked=True,
        right_blocked=True,
    )
    assert next_state(DriveState.WARNING, p, POLICY) is DriveState.STOP


def test_clearing_the_hazard_returns_to_normal():
    assert next_state(DriveState.AVOID_LEFT, perception(), POLICY) is DriveState.NORMAL


# ------------------------------------------------------------------- failsafe


def test_stale_perception_stops():
    p = perception(haz=hazard(), frame_age=99)
    assert next_state(DriveState.NORMAL, p, POLICY) is DriveState.STOP


def test_unhealthy_system_stops():
    p = perception(haz=hazard(), healthy=False)
    assert next_state(DriveState.NORMAL, p, POLICY) is DriveState.STOP


def test_failsafe_outranks_everything_including_a_clear_road():
    p = perception(haz=None, healthy=False)
    assert next_state(DriveState.NORMAL, p, POLICY) is DriveState.STOP


# ----------------------------------------------------------------- controller


def test_stop_state_commands_zero_speed():
    cmd = command_for(DriveState.STOP, POLICY)
    assert cmd.action is Action.STOP
    assert cmd.speed == 0.0


def test_avoid_left_steers_positive_and_right_negative():
    """model.py: positive steer increases heading, i.e. turns left."""
    assert command_for(DriveState.AVOID_LEFT, POLICY).steer > 0
    assert command_for(DriveState.AVOID_RIGHT, POLICY).steer < 0


def test_warning_slows_but_keeps_moving_straight():
    cmd = command_for(DriveState.WARNING, POLICY)
    assert cmd.action is Action.FORWARD
    assert cmd.steer == 0.0
    assert 0 < cmd.speed < command_for(DriveState.NORMAL, POLICY).speed


def test_every_state_maps_to_a_command():
    for state in DriveState:
        assert command_for(state, POLICY) is not None


@pytest.mark.parametrize("state", list(DriveState))
def test_commands_are_within_wire_range(state):
    cmd = command_for(state, POLICY)
    assert 0.0 <= cmd.speed <= 1.0
    assert -1.0 <= cmd.steer <= 1.0


# ------------------------------------------------------------------ hysteresis


def test_committed_manoeuvre_is_not_reconsidered_on_noise():
    """Without this the machine re-derives a side every frame and flip-flops."""
    # Committed left; the hazard's offset drifts across the centreline as the
    # robot swerves. The side must not flip.
    for offset in (+0.4, +0.05, -0.05, -0.4):
        p = perception(haz=hazard(offset=offset, urgency=Urgency.NEAR))
        assert next_state(DriveState.AVOID_LEFT, p, POLICY) is DriveState.AVOID_LEFT


def test_committed_manoeuvre_reverses_when_that_side_becomes_blocked():
    """Reacting to a newly-visible blocker is correct, not oscillation."""
    p = perception(haz=hazard(offset=+0.4, urgency=Urgency.NEAR), left_blocked=True)
    assert next_state(DriveState.AVOID_LEFT, p, POLICY) is DriveState.AVOID_RIGHT


def test_commitment_is_released_when_the_hazard_clears():
    assert next_state(DriveState.AVOID_LEFT, perception(), POLICY) is DriveState.NORMAL


def test_commitment_never_outranks_a_failsafe():
    p = perception(haz=hazard(urgency=Urgency.NEAR), healthy=False)
    assert next_state(DriveState.AVOID_LEFT, p, POLICY) is DriveState.STOP


def test_both_sides_blocked_still_stops_even_when_committed():
    p = perception(haz=hazard(urgency=Urgency.IMMINENT), left_blocked=True, right_blocked=True)
    assert next_state(DriveState.AVOID_LEFT, p, POLICY) is DriveState.STOP
