"""Every planner decision as a CAN frame: the fan-out, the config override and the byte path.

`certain_road_ros.can_link` imports no ROS, so these run everywhere: python-can's `virtual`
interface carries real frames through the library in one process (as
test_canbus_transport.py does). Where `vcan0` exists (the Jetson, after
`ros/install_gazebo_can.sh`) the same round trip runs on the real socket too.
"""

import sys
from pathlib import Path

import can
import pytest
import yaml

from certain_road.canbus.protocol import Action, Command, Mode
from certain_road.canbus.transport import (
    CanTransport,
    NullTransport,
    Transport,
    TransportConfig,
    load_transport_config,
)
from certain_road.core.paths import repo_root
from certain_road.driving.controller import command_for
from certain_road.driving.decision import DriveState, load_policy

ROOT = repo_root()
sys.path.insert(0, str(ROOT / "ros" / "certain_road_ros"))

from certain_road_ros.can_link import (  # noqa: E402
    FanoutTransport,
    can_transport_config,
    candump_text,
    describe_frame,
    open_can,
)

CANBUS = ROOT / "configs" / "canbus" / "transport.yaml"
ROS_CAN = yaml.safe_load((ROOT / "configs" / "ros" / "demo.yaml").read_text())["can"]
POLICY = load_policy(ROOT / "configs" / "driving" / "decision.yaml")
SPEED_STEP, STEER_STEP = 1 / 255, 1 / 127  # the provisional layout's quantisation
VCAN = Path("/sys/class/net/vcan0").exists()


class Broken(Transport):
    def send(self, command: Command) -> None:
        raise OSError("bus down")


def every_decision() -> list[Command]:
    return [command_for(s, POLICY) for s in DriveState]


def assert_same_command(got: Command, sent: Command) -> None:
    assert got.action is sent.action
    assert got.mode is sent.mode
    assert got.speed == pytest.approx(sent.speed, abs=SPEED_STEP / 2)
    assert got.steer == pytest.approx(sent.steer, abs=STEER_STEP / 2)


def test_fanout_gives_every_transport_the_same_command_in_order():
    a, b = NullTransport(), NullTransport()
    fan = FanoutTransport([a, b])
    for c in every_decision():
        fan.send(c)
    assert a.sent == b.sent == every_decision()


def test_a_failing_bus_never_silences_the_others():
    after = NullTransport()
    errors = []
    fan = FanoutTransport([Broken(), after], on_error=lambda t, e: errors.append(e))
    fan.send(every_decision()[0])
    assert len(after.sent) == 1
    assert [str(e) for e in errors] == ["bus down"]


def test_without_a_handler_the_failure_is_raised_after_the_others_are_sent():
    after = NullTransport()
    with pytest.raises(OSError, match="bus down"):
        FanoutTransport([Broken(), after]).send(every_decision()[0])
    assert len(after.sent) == 1


def test_ros_override_changes_only_where_the_frames_go():
    base = load_transport_config(CANBUS)
    ros = can_transport_config(CANBUS, ROS_CAN)
    assert (base.interface, base.channel) == ("virtual", "test")  # the Mac's default, untouched
    assert (ros.interface, ros.channel) == ("socketcan", "vcan0")
    assert ros.arbitration_id == base.arbitration_id == 0x101


def test_can_false_opens_nothing():
    transport, note = open_can(load_transport_config(CANBUS), "false")
    assert transport is None
    assert "can:=false" in note


def test_auto_without_the_bus_falls_back_and_says_why():
    absent = TransportConfig("socketcan", "nosuchcan9", 0x101)
    transport, note = open_can(absent, "auto")
    assert transport is None
    assert "unavailable" in note and "nosuchcan9" in note
    with pytest.raises(OSError):
        open_can(absent, "true")


def test_unknown_mode_is_refused():
    with pytest.raises(ValueError, match="auto"):
        open_can(load_transport_config(CANBUS), "maybe")


def test_every_decision_crosses_the_bus_and_decodes_to_what_was_sent():
    """The planner's byte path: command_for -> CanTransport -> bus -> Command.from_bytes."""
    cfg = TransportConfig("virtual", "ros_can_round", 0x101)
    listener = can.interface.Bus(channel=cfg.channel, interface="virtual")
    try:
        transport, _ = open_can(cfg, "true")
        fan = FanoutTransport([NullTransport(), transport])
        for c in every_decision():
            fan.send(c)
        frames = [listener.recv(timeout=1.0) for _ in every_decision()]
        fan.close()
    finally:
        listener.shutdown()
    assert all(f is not None for f in frames)
    for frame, sent in zip(frames, every_decision(), strict=True):
        assert frame.arbitration_id == 0x101 and not frame.is_extended_id
        got, line = describe_frame(frame.arbitration_id, bytes(frame.data))
        assert_same_command(got, sent)
        assert line.startswith(candump_text(0x101, sent.to_bytes()) + " -> ")


def test_readable_line_for_an_avoid_right():
    cmd = Command(Action.FORWARD, 0.35, -0.7, Mode.AUTONOMOUS)
    got, line = describe_frame(0x101, cmd.to_bytes())
    assert_same_command(got, cmd)
    assert line == "101#0159A701 -> FORWARD speed 0.35 steer -0.70 AUTONOMOUS"


@pytest.mark.parametrize(
    "payload",
    [b"\x01\x59", b"\x07\x00\x00\x01", b"\x01\x00\x80\x01", b"\x01\x00\x00\x09"],
    ids=["short", "unknown action", "steer -128", "unknown mode"],
)
def test_a_frame_that_is_not_a_command_is_reported_not_raised(payload):
    got, line = describe_frame(0x101, payload)
    assert got is None
    assert "not a drive command" in line


@pytest.mark.skipif(not VCAN, reason="vcan0 absent: run ros/install_gazebo_can.sh")
def test_the_jetson_bus_carries_the_same_bytes():
    cfg = can_transport_config(CANBUS, ROS_CAN)
    listener = can.interface.Bus(
        channel=cfg.channel,
        interface=cfg.interface,
        can_filters=[{"can_id": cfg.arbitration_id, "can_mask": 0x7FF, "extended": False}],
    )
    try:
        with CanTransport(cfg) as transport:
            for c in every_decision():
                transport.send(c)
        frames = [listener.recv(timeout=1.0) for _ in every_decision()]
    finally:
        listener.shutdown()
    for frame, sent in zip(frames, every_decision(), strict=True):
        assert frame is not None
        assert bytes(frame.data) == sent.to_bytes()
        assert_same_command(describe_frame(frame.arbitration_id, bytes(frame.data))[0], sent)
