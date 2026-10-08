"""ROS 2 survey: the survey report from any ROS camera with odometry.

A composition root like `certain_road_ros`: it may import `certain_road.survey` and
`certain_road.dashboard`, and nothing in `certain_road` may import it. It never imports
`driving/` or `canbus/`: the survey pipeline never touches the steering loop (D049).
"""
