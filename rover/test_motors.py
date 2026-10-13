"""Staged L298N motor test for the rover, run over SSH. WHEELS OFF THE GROUND.

    python rover/test_motors.py

Adapted from the friend's test_motors_l298n.py. Stages:
  1  each side, each direction, one at a time: you say which way the wheels turned
  2  deadband: the duty at which each side starts turning (you press Enter)
  3  combined moves: forward, reverse, spin left, spin right

Writes configs/rover/calibrated.yaml (direction inversions, min_duty from the deadband), which
overrides configs/rover/rover.yaml for every rover script.

SAFETY: Ctrl-C stops both motors. Keep a hand on the battery switch.
"""

from __future__ import annotations

import select
import signal
import sys
import time
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from drivemap import CALIBRATED, load_config  # noqa: E402
from hardware import SIDES, Motors  # noqa: E402

from certain_road.core.paths import repo_root  # noqa: E402

TEST_DUTY = 60.0
DEADBAND_MARGIN = 5.0  # min_duty = the slower side's start duty + this
STEP_S = 0.35


def ask(prompt: str) -> str:
    try:
        return input(prompt).strip().lower()
    except EOFError:
        return ""


def run(m: Motors, left: float, right: float, seconds: float) -> None:
    m.set(left, right)
    time.sleep(seconds)
    m.stop()
    time.sleep(0.3)


def main() -> None:
    if ask("Wheels OFF the ground and battery switch in reach? [yes/no] ") != "yes":
        sys.exit("Not starting.")
    cfg = load_config()
    m = Motors(cfg)
    signal.signal(signal.SIGTERM, lambda *_: (m.close(), sys.exit(0)))
    mode = "PWM on pins 32/33" if cfg["use_pwm"] else "jumper mode (ENA/ENB jumpers fitted)"
    print(f"motors ready: {mode}")
    found: dict = {}
    try:
        print("\n=== 1. direction, one side at a time ===")
        for side in SIDES:
            if ask(f"\nSpin the {side} side FORWARD for 2 s? [Enter = go, s = skip] ") == "s":
                continue
            run(m, *((TEST_DUTY, 0) if side == "left" else (0, TEST_DUTY)), 2.0)
            r = ask(f"Did the {side} wheels turn the rover's FORWARD way? [y/n/none] ")
            if r.startswith("n"):
                found[f"invert_{side}"] = not cfg[f"invert_{side}"]
                cfg[f"invert_{side}"] = found[f"invert_{side}"]
                print(f"  -> {side} side will be inverted")
            elif r in ("", "none"):
                print(
                    "  -> nothing moved: check the motor wires, the battery, the ENA/ENB "
                    "jumpers (jumper mode) and the common ground (Jetson pin 30 to L298N GND)"
                )

        print("\n=== 2. deadband: press Enter the moment the wheels start turning ===")
        start = {}
        for side in SIDES:
            if ask(f"\nRamp the {side} side? [Enter = go, s = skip] ") == "s":
                continue
            for duty in range(0, 101, 5):
                m.set(*((duty, 0) if side == "left" else (0, duty)))
                print(f"\r  duty {duty:>3} %", end="", flush=True)
                if select.select([sys.stdin], [], [], STEP_S)[0]:
                    sys.stdin.readline()
                    start[side] = duty
                    break
            m.stop()
            print(f"\n  {side} starts at {start.get(side, '>100')} %")
        if start:
            found["min_duty"] = float(min(100, max(start.values()) + DEADBAND_MARGIN))
            found["max_duty"] = float(max(cfg["max_duty"], found["min_duty"] + 10))

        print("\n=== 3. combined moves, 1.5 s each ===")
        d = TEST_DUTY
        for name, left, right in [
            ("forward", d, d),
            ("reverse", -d, -d),
            ("spin left", -d, d),
            ("spin right", d, -d),
        ]:
            if ask(f"\n{name}: [Enter = go, s = skip] ") != "s":
                run(m, left, right, 1.5)
    finally:
        m.close()
        print("motors stopped, GPIO released")
    if found:
        out = repo_root() / CALIBRATED
        old = yaml.safe_load(out.read_text()) if out.exists() else {}
        out.write_text(yaml.safe_dump({**(old or {}), **found}, sort_keys=False))
        print(f"saved {found} -> {out}")


if __name__ == "__main__":
    main()
