"""The planner's Command becomes the right pair of motor duties on the rover (no hardware)."""

import sys

import pytest

from certain_road.canbus.protocol import Action, Command, Mode
from certain_road.core.paths import repo_root

sys.path.insert(0, str(repo_root() / "rover"))

from drivemap import command_duties, load_config  # noqa: E402

CFG = load_config()


def cmd(action=Action.FORWARD, speed=1.0, steer=0.0) -> Command:
    return Command(action, speed, steer, Mode.AUTONOMOUS)


def test_stop_is_both_motors_off():
    assert command_duties(cmd(Action.STOP, 0.0, 0.0), CFG) == (0.0, 0.0)


def test_cruise_drives_straight_at_max_duty():
    assert command_duties(cmd(speed=1.0), CFG) == (CFG["max_duty"], CFG["max_duty"])


def test_any_forward_speed_stays_above_the_deadband():
    left, right = command_duties(cmd(speed=0.05), CFG)
    assert left >= CFG["min_duty"] and right >= CFG["min_duty"]


@pytest.mark.parametrize(("steer", "faster"), [(0.7, "right"), (-0.7, "left")])
def test_positive_steer_turns_left(steer, faster):
    """controller.py: positive steer is left, so the right side must run faster."""
    left, right = command_duties(cmd(speed=0.35, steer=steer), CFG)
    assert (right > left) if faster == "right" else (left > right)


def test_heading_hold_adds_a_left_turn_when_positive():
    left, right = command_duties(cmd(speed=1.0), CFG, hold=10.0)
    assert right - left == pytest.approx(20.0)


def test_reverse_mirrors_forward():
    fl, fr = command_duties(cmd(speed=0.5, steer=0.3), CFG)
    rl, rr = command_duties(cmd(Action.REVERSE, 0.5, 0.3), CFG)
    assert (rl, rr) == (-fl, -fr)


def test_duties_never_exceed_full_scale():
    left, right = command_duties(cmd(speed=1.0, steer=1.0), CFG, hold=100.0)
    assert -100.0 <= left <= 100.0 and -100.0 <= right <= 100.0
