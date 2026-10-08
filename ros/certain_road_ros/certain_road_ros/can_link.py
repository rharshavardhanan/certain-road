"""Each `Command` onto the CAN bus beside /cmd_vel, and frames back off it as readable text.

Pure python-can and `certain_road.canbus`, no ROS, so the byte path is tested anywhere.

- `FanoutTransport` hands one `Command` to several `Transport`s. The planner gives it
  `RosTransport` and `CanTransport`, so a decision leaves as a Twist and as a CAN frame from
  the same object `driving/` already talks to (D049, D052). A CAN send that fails is
  reported and never stops /cmd_vel.
- `can_transport_config` is `configs/canbus/transport.yaml` with the ROS demo's interface
  and channel laid over it (`configs/ros/demo.yaml`, `can`). The canbus file keeps the
  Mac's python-can `virtual` default; the arbitration ID and the provisional 4-byte layout
  stay in one place.
- `describe_frame` is what `can_monitor_node` prints: the frame as `candump` shows it, then
  `Command.from_bytes` of its payload.
"""

from __future__ import annotations

import struct
from collections.abc import Callable, Sequence
from dataclasses import replace
from pathlib import Path

import can

from certain_road.canbus.protocol import Command
from certain_road.canbus.transport import (
    CanTransport,
    Transport,
    TransportConfig,
    load_transport_config,
)

CAN_MODES = ("auto", "true", "false")


class FanoutTransport(Transport):
    """One `Command`, every transport, in order.

    Without `on_error` a failing transport raises after the others have been sent to;
    with it, the failure is handed over and the rest carry on."""

    def __init__(
        self,
        transports: Sequence[Transport],
        on_error: Callable[[Transport, Exception], None] | None = None,
    ) -> None:
        self.transports = list(transports)
        self._on_error = on_error

    def send(self, command: Command) -> None:
        failed: list[Exception] = []
        for t in self.transports:
            try:
                t.send(command)
            except Exception as exc:  # one bad bus must not silence the others
                if self._on_error is None:
                    failed.append(exc)
                else:
                    self._on_error(t, exc)
        if failed:
            raise failed[0]

    def close(self) -> None:
        for t in self.transports:
            t.close()


def can_transport_config(base: Path, override: dict) -> TransportConfig:
    """The canbus config with `override`'s interface and channel, where it gives them."""
    cfg = load_transport_config(base)
    return replace(
        cfg,
        interface=str(override.get("interface", cfg.interface)),
        channel=str(override.get("channel", cfg.channel)),
    )


def open_can(config: TransportConfig, mode: str) -> tuple[CanTransport | None, str]:
    """(transport or None, what happened). `mode` is auto, true or false.

    auto opens the bus if it can and says why not otherwise; true raises if it cannot."""
    if mode not in CAN_MODES:
        raise ValueError(f"can must be one of {CAN_MODES}, got {mode!r}")
    where = f"{config.interface}/{config.channel} id 0x{config.arbitration_id:X}"
    if mode == "false":
        return None, "CAN off (can:=false): commands leave as /cmd_vel only"
    try:
        transport = CanTransport(config)
    except (OSError, can.CanError) as exc:
        if mode == "true":
            raise
        return None, f"CAN unavailable on {where} ({exc}): commands leave as /cmd_vel only"
    return transport, f"CAN on {where}: every command also leaves as a CAN frame"


def candump_text(arbitration_id: int, data: bytes) -> str:
    """The frame in `candump -L`'s compact notation, e.g. `101#0159A701`."""
    return f"{arbitration_id:03X}#{bytes(data).hex().upper()}"


def describe_command(command: Command) -> str:
    return (
        f"{command.action.name} speed {command.speed:.2f} steer {command.steer:+.2f} "
        f"{command.mode.name}"
    )


def describe_frame(arbitration_id: int, data: bytes) -> tuple[Command | None, str]:
    """(the decoded command or None, one readable line). A payload that is not a valid
    4-byte command decodes to None and says why, rather than raising."""
    raw = candump_text(arbitration_id, data)
    try:
        command = Command.from_bytes(bytes(data))
    except (struct.error, ValueError) as exc:  # wrong length; unknown enum or out of range
        return None, f"{raw} -> not a drive command ({exc})"
    return command, f"{raw} -> {describe_command(command)}"
