"""ROS 2 Jazzy demo of the drive pipeline (D093).

A composition root like `certain_road.sim`: its nodes may import `driving/`, `canbus/`
and `sim/`, and nothing in `certain_road` may import it. The decision code runs
unchanged; this package only moves its inputs and outputs over ROS topics.
"""
