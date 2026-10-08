#!/usr/bin/env bash
# Part 3: the real clip through ROS 2, every decision as a CAN frame.  Usage: [start_s] [end_s]
# Opens a second terminal with the decoded CAN frames. Stops by itself at the window's end.
source "$(dirname "$0")/_common.sh"
can_window
run_launch certain_road_ros video.launch.py start:="${1:-120}" end:="${2:-180}" can:=auto rviz:="$RVIZ"
