"""T14 — OBD-II decoding, exercised against a real bus with a fake ECU.

python-can's `virtual` interface is cross-platform, so these are genuine frames
being encoded, transmitted, received and decoded — not a mocked bus. The bugs
worth catching here (wrong reply id, unchecked PID echo) all live in exactly the
part a mock would replace.
"""

import threading

import can
import pytest

from certain_road.canbus.obd import (
    FUNCTIONAL_REQUEST_ID,
    PID_ENGINE_RPM,
    PID_VEHICLE_SPEED,
    NullObdReader,
    ObdReader,
    parse_response,
    request_frame,
)


class FakeEcu(threading.Thread):
    """Answers mode-01 queries on 0x7E8, the way a real ECU would."""

    def __init__(self, channel: str, speed: int, rpm_quarters: int) -> None:
        super().__init__(daemon=True)
        self.channel, self.speed, self.rpm_quarters = channel, speed, rpm_quarters
        # NOT `_stop`: threading.Thread._stop is an internal method and
        # shadowing it breaks join().
        self._stopping = threading.Event()

    def run(self) -> None:
        with can.interface.Bus(channel=self.channel, interface="virtual") as bus:
            while not self._stopping.is_set():
                msg = bus.recv(timeout=0.05)
                if msg is None or msg.arbitration_id != FUNCTIONAL_REQUEST_ID:
                    continue
                pid = msg.data[2]
                if pid == PID_VEHICLE_SPEED:
                    payload = [0x03, 0x41, pid, self.speed, 0, 0, 0, 0]
                elif pid == PID_ENGINE_RPM:
                    payload = [0x04, 0x41, pid,
                               self.rpm_quarters >> 8, self.rpm_quarters & 0xFF, 0, 0, 0]
                else:
                    continue
                bus.send(can.Message(arbitration_id=0x7E8, data=payload, is_extended_id=False))

    def stop(self) -> None:
        self._stopping.set()
        self.join(timeout=1.0)


def test_request_frame_is_the_documented_eight_bytes():
    assert request_frame(PID_VEHICLE_SPEED) == bytes([0x02, 0x01, 0x0D, 0, 0, 0, 0, 0])


def test_speed_decodes_from_one_byte():
    assert parse_response(0x7E8, bytes([0x03, 0x41, 0x0D, 87, 0, 0, 0, 0]),
                          PID_VEHICLE_SPEED) == 87.0


def test_rpm_uses_quarter_resolution():
    # 0x0F 0xA0 = 4000 quarters = 1000 rpm
    assert parse_response(0x7E8, bytes([0x04, 0x41, 0x0C, 0x0F, 0xA0, 0, 0, 0]),
                          PID_ENGINE_RPM) == 1000.0


@pytest.mark.parametrize("arb", [0x7DF, 0x123, 0x7F0])
def test_replies_outside_the_ecu_id_range_are_ignored(arb):
    """0x7DF is where we transmit; a 'reply' there is our own frame echoed."""
    assert parse_response(arb, bytes([0x03, 0x41, 0x0D, 60, 0, 0, 0, 0]),
                          PID_VEHICLE_SPEED) is None


def test_a_reply_for_a_different_pid_is_rejected():
    """RPM's first data byte would decode as a perfectly plausible speed."""
    rpm_reply = bytes([0x04, 0x41, PID_ENGINE_RPM, 0x0F, 0xA0, 0, 0, 0])
    assert parse_response(0x7E8, rpm_reply, PID_VEHICLE_SPEED) is None


def test_negative_response_is_rejected():
    assert parse_response(0x7E8, bytes([0x03, 0x7F, 0x0D, 0x12, 0, 0, 0, 0]),
                          PID_VEHICLE_SPEED) is None


def test_truncated_frame_is_rejected():
    assert parse_response(0x7E8, bytes([0x03, 0x41]), PID_VEHICLE_SPEED) is None


def test_reads_speed_and_rpm_from_a_live_virtual_bus():
    channel = "obd-test-live"
    ecu = FakeEcu(channel, speed=64, rpm_quarters=3200)
    ecu.start()
    try:
        with can.interface.Bus(channel=channel, interface="virtual") as bus:
            reading = ObdReader(bus, timeout_s=1.0).read()
    finally:
        ecu.stop()
    assert reading.speed_kmh == 64.0
    assert reading.rpm == 800.0


def test_silent_bus_yields_none_not_zero():
    """No ECU answering. None means unknown; 0.0 would mean 'stopped'."""
    with can.interface.Bus(channel="obd-test-silent", interface="virtual") as bus:
        reading = ObdReader(bus, timeout_s=0.05).read()
    assert reading.speed_kmh is None and reading.rpm is None


def test_null_reader_reports_unknown():
    reading = NullObdReader().read()
    assert reading.speed_kmh is None and reading.rpm is None
