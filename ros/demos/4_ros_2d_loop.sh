#!/usr/bin/env bash
# Part 4: the ROS 2 closed loop on the 2D simulator (projected boxes), CAN on. Ctrl+C stops.
source "$(dirname "$0")/_common.sh"
can_window
run_launch certain_road_ros demo.launch.py can:=auto rviz:="$RVIZ"
