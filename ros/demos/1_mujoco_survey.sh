#!/usr/bin/env bash
# Part 1: MuJoCo road, Model P + B live, survey and result screen.  Usage: [preset] [seed]
# The road build takes ~3.5 min before the drive starts. Esc or q stops early.
source "$(dirname "$0")/_common.sh"
exec .venv/bin/python -m sim.mujoco.demo --preset "${1:-poor}" --seed "${2:-0}"
