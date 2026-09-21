"""T14 — read vehicle speed and RPM from OBD-II over CAN.

The read side of the bus. `canbus/protocol.py` and `canbus/transport.py` send
drive commands; this asks the vehicle what it is doing, which the survey needs to
geotag detections by dead reckoning between GPS fixes.

**Request/response is asymmetric on purpose.** A mode-01 query goes to the
functional broadcast id `0x7DF`; ECUs answer on their own physical ids,
`0x7E8`–`0x7EF`. Listening on `0x7DF` for the reply — the obvious mistake — hears
nothing, because nobody transmits there but us.

A reply is only accepted when `data[1] == 0x41` (positive response to mode 01)
*and* `data[2]` echoes the PID asked for. Without the PID check, a concurrent
query for a different PID gets parsed as this one and produces a plausible wrong
number: RPM's first byte read as a speed is a perfectly believable 0–255 km/h.
"""

import struct
import time
from dataclasses import dataclass

FUNCTIONAL_REQUEST_ID = 0x7DF
RESPONSE_ID_RANGE = range(0x7E8, 0x7F0)
MODE_CURRENT_DATA = 0x01
POSITIVE_RESPONSE = 0x41

PID_ENGINE_RPM = 0x0C
PID_VEHICLE_SPEED = 0x0D


def request_frame(pid: int) -> bytes:
    """Mode-01 single-PID query, padded to the 8 bytes CAN expects."""
    return struct.pack("BBBBBBBB", 0x02, MODE_CURRENT_DATA, pid, 0, 0, 0, 0, 0)


def parse_response(arbitration_id: int, data: bytes, pid: int) -> float | None:
    """Decode a reply, or None if it is not a positive answer to `pid`."""
    if arbitration_id not in RESPONSE_ID_RANGE or len(data) < 4:
        return None
    if data[1] != POSITIVE_RESPONSE or data[2] != pid:
        return None
    if pid == PID_VEHICLE_SPEED:
        return float(data[3])                       # km/h, one byte, no scaling
    if pid == PID_ENGINE_RPM:
        if len(data) < 5:
            return None
        return (256.0 * data[3] + data[4]) / 4.0    # quarter-RPM resolution
    return None


@dataclass(frozen=True)
class Reading:
    speed_kmh: float | None
    rpm: float | None
    t_monotonic: float


class ObdReader:
    """Polls speed and RPM over a python-can bus.

    The bus is injected rather than constructed here so the same code runs
    against `socketcan` on the Jetson and against python-can's cross-platform
    `virtual` bus in tests — the tests exercise real frame encoding and decoding,
    not a mock of it.
    """

    def __init__(self, bus, *, timeout_s: float = 0.2) -> None:
        self._bus = bus
        self._timeout_s = timeout_s

    def _query(self, pid: int) -> float | None:
        import can

        self._bus.send(can.Message(arbitration_id=FUNCTIONAL_REQUEST_ID,
                                   data=request_frame(pid), is_extended_id=False))
        deadline = time.monotonic() + self._timeout_s
        while time.monotonic() < deadline:
            msg = self._bus.recv(timeout=max(0.0, deadline - time.monotonic()))
            if msg is None:
                break
            value = parse_response(msg.arbitration_id, bytes(msg.data), pid)
            if value is not None:
                return value
        return None

    def read(self) -> Reading:
        return Reading(speed_kmh=self._query(PID_VEHICLE_SPEED),
                       rpm=self._query(PID_ENGINE_RPM),
                       t_monotonic=time.monotonic())


class NullObdReader:
    """`--can none`. Returns no data rather than zero.

    Zero is a real speed and would be dead-reckoned as a stationary vehicle;
    None means "unknown" and lets the caller fall back to GPS.
    """

    def read(self) -> Reading:
        return Reading(speed_kmh=None, rpm=None, t_monotonic=time.monotonic())
