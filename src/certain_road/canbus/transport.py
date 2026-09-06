"""Where a `Command` actually goes.

**The point of this module.** `driving/` decides *what* the vehicle should do and
hands over a `Command`. It never learns how that command reaches a motor. That
separation is what makes the decision core vehicle-agnostic (D052): moving from a
laptop, to a Jetson emitting frames on a virtual bus, to a real vehicle on a real
bus is a change of configuration, not of logic.

**Two implementations, deliberately not three.** An earlier design also carried a
`SerialTransport` as insurance against CAN hardware not arriving. SocketCAN's
virtual interface removed that need — real CAN frames need no transceiver — so
the serial path is not built. If a serial-only vehicle ever turns up, it is a new
`Transport` subclass and nothing else moves.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path

import yaml

from certain_road.canbus.protocol import Command


@dataclass(frozen=True)
class TransportConfig:
    interface: str
    channel: str
    arbitration_id: int


def load_transport_config(path: Path) -> TransportConfig:
    raw = yaml.safe_load(Path(path).read_text())
    arb = raw["arbitration_id"]
    return TransportConfig(
        interface=str(raw["interface"]),
        channel=str(raw["channel"]),
        arbitration_id=int(arb, 0) if isinstance(arb, str) else int(arb),
    )


class Transport(ABC):
    """Somewhere a `Command` can be sent."""

    @abstractmethod
    def send(self, command: Command) -> None: ...

    def close(self) -> None:  # pragma: no cover - default is a no-op
        return None

    def __enter__(self) -> Transport:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()


class NullTransport(Transport):
    """Records commands and sends them nowhere.

    For bench tests and for running the decision logic with no bus present — which
    is most of the development on this project.
    """

    def __init__(self) -> None:
        self.sent: list[Command] = []

    def send(self, command: Command) -> None:
        self.sent.append(command)


class CanTransport(Transport):
    """Emits real CAN frames via `python-can`.

    Identical code on every target; only `TransportConfig` differs. On the Jetson
    with `interface='socketcan', channel='vcan0'` these are genuine frames on a
    genuine socket, watchable with `candump vcan0` — not a mock.
    """

    def __init__(self, config: TransportConfig) -> None:
        import can  # imported here so the package is usable without a bus present

        self.config = config
        self._bus = can.interface.Bus(channel=config.channel, interface=config.interface)
        self._message = can.Message

    def send(self, command: Command) -> None:
        self._bus.send(
            self._message(
                arbitration_id=self.config.arbitration_id,
                data=command.to_bytes(),
                is_extended_id=False,
            )
        )

    def close(self) -> None:
        self._bus.shutdown()
