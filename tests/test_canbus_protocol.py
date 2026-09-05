"""Tests for the provisional Command <-> bytes encoding.

`canbus/protocol.py` is pure data: no dependency on driving/, no dependency
on hardware. The byte layout here is explicitly provisional -- see the module
docstring -- pending the lab robot's actual controller protocol.
"""

import ast
from pathlib import Path

import pytest

from certain_road.canbus.protocol import Action, Command, Mode

REPO_ROOT = Path(__file__).resolve().parents[1]
PROTOCOL_SOURCE = REPO_ROOT / "src" / "certain_road" / "canbus" / "protocol.py"


def test_protocol_module_imports_nothing_from_driving():
    """canbus/protocol.py must stay pure data -- no dependency on driving/."""
    tree = ast.parse(PROTOCOL_SOURCE.read_text())
    imported = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported += [alias.name for alias in node.names]
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.append(node.module)

    assert not any("driving" in name for name in imported), imported


def test_command_round_trips_through_bytes():
    cmd = Command(action=Action.FORWARD, speed=0.5, steer=-0.25, mode=Mode.AUTONOMOUS)
    encoded = cmd.to_bytes()

    assert isinstance(encoded, bytes)
    assert len(encoded) == 4

    decoded = Command.from_bytes(encoded)
    assert decoded.action == cmd.action
    assert decoded.mode == cmd.mode
    assert decoded.speed == pytest.approx(cmd.speed, abs=1 / 255)
    assert decoded.steer == pytest.approx(cmd.steer, abs=1 / 127)


def test_command_extremes_round_trip_exactly():
    full_right = Command(action=Action.FORWARD, speed=1.0, steer=1.0, mode=Mode.MANUAL)
    full_left = Command(action=Action.STOP, speed=0.0, steer=-1.0, mode=Mode.MANUAL)

    assert Command.from_bytes(full_right.to_bytes()) == full_right
    assert Command.from_bytes(full_left.to_bytes()) == full_left


def test_speed_out_of_range_is_rejected():
    with pytest.raises(ValueError):
        Command(action=Action.FORWARD, speed=1.5, steer=0.0, mode=Mode.AUTONOMOUS)
    with pytest.raises(ValueError):
        Command(action=Action.FORWARD, speed=-0.1, steer=0.0, mode=Mode.AUTONOMOUS)


def test_steer_out_of_range_is_rejected():
    with pytest.raises(ValueError):
        Command(action=Action.FORWARD, speed=0.5, steer=1.5, mode=Mode.AUTONOMOUS)
    with pytest.raises(ValueError):
        Command(action=Action.FORWARD, speed=0.5, steer=-1.5, mode=Mode.AUTONOMOUS)
