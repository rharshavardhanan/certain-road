"""The stand-in driver's rule, without ROS: when to steer, and how hard. NOT UNDER TEST.

`lane_keeper_node` holds the Gazebo car in its lane the way a driver would, so a 500 m
closed-loop run tests the planner's reactions to potholes rather than its lack of a lane
keeper (NORMAL means steer 0). This module is that driver's whole policy:

- `yaw_rate`: a proportional return to the lane centre from the true lateral offset and
  heading (configs/ros/demo.yaml `lane_keeper`).
- `blend`: the Twist the car receives. In the states the stand-in `steers_in` (NORMAL,
  WARNING) it is the planner's speed with the stand-in's yaw rate; in every other state
  (AVOID_LEFT, AVOID_RIGHT, STOP) it is the planner's Twist, unchanged. The speed is always
  the planner's.

Nothing here reaches the CAN bus: the frames carry the planner's own Command.
"""

from __future__ import annotations

import math


def yaw_rate(lateral_m: float, heading_rad: float, cfg: dict) -> float:
    """rad/s back toward the lane centre. `lateral_m` is left of it, `heading_rad` from the
    road's direction, anticlockwise; both positive turn the car right (negative yaw rate)."""
    w = -(cfg["k_lateral"] * lateral_m + cfg["k_heading"] * heading_rad)
    return max(-cfg["max_yaw_rate"], min(cfg["max_yaw_rate"], w))


def heading(qw: float, qx: float, qy: float, qz: float) -> float:
    """Yaw of a quaternion, anticlockwise from +x."""
    return math.atan2(2 * (qw * qz + qx * qy), 1 - 2 * (qy * qy + qz * qz))


def blend(
    state: str, planner: tuple[float, float], keeper_yaw_rate: float, cfg: dict
) -> tuple[tuple[float, float], bool]:
    """((linear m/s, yaw rate rad/s) to send, whether the stand-in is steering)."""
    linear, planner_yaw = planner
    if state in cfg["steers_in"] and linear != 0.0:
        return (linear, keeper_yaw_rate), True
    return (linear, planner_yaw), False
