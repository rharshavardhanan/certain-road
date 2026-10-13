"""From the planner's Command to the two motor duties of a skid-steer rover (no hardware).

The planner speaks in `canbus.protocol.Command`: an action, a speed 0..1 and a steer -1..1
(positive turns left, `driving/controller.py`). The rover's L298N wants a duty -100..100 per
side. Speed maps onto [min_duty, max_duty], because a TT gear motor stalls below its deadband;
steer adds +/- turn_duty, the right side faster to turn left. Heading hold, when on, adds its
correction in NORMAL and WARNING only: steering around a pothole is the planner's alone.
"""

from __future__ import annotations

from pathlib import Path

import yaml

from certain_road.canbus.protocol import Action, Command
from certain_road.core.paths import repo_root

CONFIG = Path("configs/rover/rover.yaml")
CALIBRATED = Path("configs/rover/calibrated.yaml")


def load_config(root: Path | None = None) -> dict:
    """rover.yaml, overridden by calibrated.yaml where rover/test_motors.py measured a value."""
    root = root or repo_root()
    cfg = yaml.safe_load((root / CONFIG).read_text())
    if (root / CALIBRATED).exists():
        cfg.update(yaml.safe_load((root / CALIBRATED).read_text()) or {})
    return cfg


def clamp(v: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, v))


def command_duties(command: Command, cfg: dict, hold: float = 0.0) -> tuple[float, float]:
    """(left, right) duty in -100..100 for one Command. `hold` is the heading-hold turn, in
    duty %, positive left, applied by the caller only in NORMAL and WARNING."""
    if command.action is Action.STOP or command.speed <= 0.0:
        return 0.0, 0.0
    base = cfg["min_duty"] + command.speed * (cfg["max_duty"] - cfg["min_duty"])
    turn = command.steer * cfg["turn_duty"] + hold
    left, right = base - turn, base + turn
    if command.action is Action.REVERSE:
        left, right = -left, -right
    return clamp(left, -100.0, 100.0), clamp(right, -100.0, 100.0)
