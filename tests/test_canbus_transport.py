"""The transport layer, exercised on a real CAN bus.

python-can's `virtual` interface is cross-platform, so these are genuine
send/receive round trips through the library — not mocks. On the Jetson the only
change is `interface: socketcan, channel: vcan0`, which is why this coverage
carries over to the real thing.
"""

import can
import pytest

from certain_road.canbus.protocol import Action, Command, Mode
from certain_road.canbus.transport import (
    CanTransport,
    NullTransport,
    TransportConfig,
    load_transport_config,
)
from certain_road.core.paths import repo_root

CONFIG_PATH = repo_root() / "configs" / "canbus" / "transport.yaml"


def a_command(steer: float = 0.0) -> Command:
    return Command(Action.FORWARD, 0.4, steer, Mode.AUTONOMOUS)


def test_config_parses_hex_arbitration_id():
    cfg = load_transport_config(CONFIG_PATH)
    assert cfg.arbitration_id == 0x101


def test_null_transport_records_without_a_bus():
    t = NullTransport()
    t.send(a_command())
    t.send(a_command(steer=0.5))
    assert len(t.sent) == 2
    assert t.sent[1].steer == 0.5


def test_can_transport_puts_a_real_frame_on_the_bus():
    cfg = TransportConfig(interface="virtual", channel="t_send", arbitration_id=0x101)
    listener = can.interface.Bus(channel="t_send", interface="virtual")
    try:
        with CanTransport(cfg) as transport:
            transport.send(a_command(steer=0.5))
        msg = listener.recv(timeout=1.0)
    finally:
        listener.shutdown()

    assert msg is not None, "no frame reached the bus"
    assert msg.arbitration_id == 0x101
    assert msg.is_extended_id is False
    assert len(msg.data) == 4


def test_frame_payload_round_trips_back_to_the_command():
    """The wire format is the contract: what goes out must decode to what was sent."""
    cfg = TransportConfig(interface="virtual", channel="t_round", arbitration_id=0x101)
    listener = can.interface.Bus(channel="t_round", interface="virtual")
    original = Command(Action.FORWARD, 0.4, -0.7, Mode.AUTONOMOUS)
    try:
        with CanTransport(cfg) as transport:
            transport.send(original)
        msg = listener.recv(timeout=1.0)
    finally:
        listener.shutdown()

    decoded = Command.from_bytes(bytes(msg.data))
    assert decoded.action is original.action
    assert decoded.mode is original.mode
    assert decoded.steer == pytest.approx(original.steer, abs=0.01)
    assert decoded.speed == pytest.approx(original.speed, abs=0.01)


def test_stop_command_is_transmissible():
    """The safety command must survive the wire like any other."""
    cfg = TransportConfig(interface="virtual", channel="t_stop", arbitration_id=0x101)
    listener = can.interface.Bus(channel="t_stop", interface="virtual")
    try:
        with CanTransport(cfg) as transport:
            transport.send(Command(Action.STOP, 0.0, 0.0, Mode.AUTONOMOUS))
        msg = listener.recv(timeout=1.0)
    finally:
        listener.shutdown()

    decoded = Command.from_bytes(bytes(msg.data))
    assert decoded.action is Action.STOP
    assert decoded.speed == 0.0
