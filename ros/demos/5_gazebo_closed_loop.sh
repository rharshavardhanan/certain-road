#!/usr/bin/env bash
# Part 5: Gazebo closed loop: camera -> Model P + B -> planner -> lane keeper -> car, CAN on.
# Usage: [noon|morning|evening|overcast]. Runs at 0.3x real time so perception sees every frame.
# Opens a second terminal with the decoded CAN frames. Ctrl+C stops.
source "$(dirname "$0")/_common.sh"
light=${1:-noon}
world="$REPO/runs/gazebo/poor_seed0/world.sdf"
[ "$light" != noon ] && world="$REPO/runs/gazebo/poor_seed0/world_${light}.sdf"
[ -f "$world" ] || { echo "!! no $world (python -m sim.gazebo.export --preset poor --seed 0 --sdf-only --light all)"; exit 1; }
can_window
run_launch certain_road_ros gazebo.launch.py world:="$world" rtf:=0.3 can:=true rviz:="$RVIZ"
