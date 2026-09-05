"""Command <-> bytes: the robot's control-transport wire format.

PROVISIONAL. The real CAN frame layout cannot be finalised until the lab
robot's controller protocol is known -- that is an open blocker (see
docs/superpowers/plans/2026-09-05-day5-corridor-sim.md, "A judgement call I
want you to make and report"). This module gives `Command` a byte encoding
that round-trips correctly today so the simulator and any transport built
against it have something concrete to target. The exact byte positions and
scale factors below are placeholders to be replaced once the controller's
actual protocol is read off hardware -- nothing here should be treated as a
spec to build firmware against.

Layout (4 bytes, provisional):

    byte 0  action   Action, one of {STOP, FORWARD, REVERSE}   (unsigned u8)
    byte 1  speed    unsigned 0..255, linear map of speed in [0.0, 1.0]
    byte 2  steer    SIGNED 8-bit, -127..127, linear map of steer in
                     [-1.0, 1.0] (see "signed steering" below)
    byte 3  mode     Mode, one of {MANUAL, AUTONOMOUS}          (unsigned u8)

Signed steering. A single byte's two's-complement range is -128..127, which
is asymmetric -- there is one more negative code point than positive. Scaling
by 128 would make steer=-1.0 encode exactly (-128) but leave +1.0 unreachable
at full scale (it would land on 128, which does not fit), forcing a silent
clamp on encode that decode could never undo. This module scales by 127 in
both directions instead: steer=+1.0 -> +127, steer=-1.0 -> -127. That gives
up the single code point -128, but every value in [-1.0, 1.0] then has an
exact, symmetric round trip at both extremes. Encoding uses `struct`'s
signed-char format ('b') rather than hand-rolled two's-complement arithmetic.

`canbus/` must never import `driving/` (see `.importlinter`): this module is
pure data, with zero dependency on the corridor/decision logic that produces
a `Command`.
"""

from __future__ import annotations

import struct
from dataclasses import dataclass
from enum import IntEnum

_SPEED_SCALE = 255  # speed in [0.0, 1.0] -> unsigned byte 0..255
_STEER_SCALE = 127  # steer in [-1.0, 1.0] -> signed byte -127..127 (see module docstring)

_STRUCT_FORMAT = "BBbB"  # action (u8), speed (u8), steer (signed i8), mode (u8)


class Action(IntEnum):
    """Coarse-grained drive command. Steering direction is carried by
    `Command.steer`, not by a separate action value."""

    STOP = 0
    FORWARD = 1
    REVERSE = 2


class Mode(IntEnum):
    """Who is authoring commands right now."""

    MANUAL = 0
    AUTONOMOUS = 1


@dataclass(frozen=True)
class Command:
    """One control command, transport-agnostic.

    `speed` and `steer` are always normalised floats; `to_bytes`/`from_bytes`
    own the wire-format scaling so callers never think in byte units.
    """

    action: Action
    speed: float
    steer: float
    mode: Mode

    def __post_init__(self) -> None:
        if not 0.0 <= self.speed <= 1.0:
            raise ValueError(f"speed must be in [0.0, 1.0], got {self.speed!r}")
        if not -1.0 <= self.steer <= 1.0:
            raise ValueError(f"steer must be in [-1.0, 1.0], got {self.steer!r}")

    def to_bytes(self) -> bytes:
        """Encode per the provisional 4-byte layout in the module docstring."""
        speed_byte = round(self.speed * _SPEED_SCALE)
        steer_byte = round(self.steer * _STEER_SCALE)
        return struct.pack(_STRUCT_FORMAT, int(self.action), speed_byte, steer_byte, int(self.mode))

    @classmethod
    def from_bytes(cls, data: bytes) -> Command:
        """Decode the provisional 4-byte layout back into a `Command`."""
        action_byte, speed_byte, steer_byte, mode_byte = struct.unpack(_STRUCT_FORMAT, data)
        return cls(
            action=Action(action_byte),
            speed=speed_byte / _SPEED_SCALE,
            steer=steer_byte / _STEER_SCALE,
            mode=Mode(mode_byte),
        )
