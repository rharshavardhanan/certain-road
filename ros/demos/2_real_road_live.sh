#!/usr/bin/env bash
# Part 2: the real Indian road clip with Model P + B live and the ground-truth strip (no ROS).
source "$(dirname "$0")/_common.sh"
exec .venv/bin/python scripts/live_video.py data/video/2DV-cYmIvT4.mp4
