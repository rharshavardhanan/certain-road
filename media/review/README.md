# Review recordings (2026-10-06 to 2026-10-08, Jetson Orin Nano)

Compressed copies for GitHub: H.264, at most 1280 px wide, about 1.5 Mbit/s. The
full-quality originals stay on the Jetson (`review_backup/`, `runs/`, gitignored). Every
recording plays at real speed; live, the Jetson runs these at 0.2–0.4x. The order and what
to say are in [`ros/MENTOR-DEMO.md`](../../ros/MENTOR-DEMO.md).

| File | Shows | Decision |
|---|---|---|
| `1_mujoco_survey_drive.mp4` | MuJoCo road from CC BY photos: Model P + B live, survey, vision-estimated PCI per segment, result screen against exact ground truth | D087–D094 |
| `2_real_road_model_p_b_live.mp4` | Real Indian dashcam clip (RT Dashcam, CC BY), 120–180 s: P + B live, ground-truth strip, Model P caught 12 of 17 counted potholes | D094 |
| `3_ros_real_video_can.mp4` | The same clip through ROS 2: perception, planner, every decision as a CAN frame on vcan0, decoded. Open loop: a recording cannot be steered | D095 |
| `4_ros_2d_closed_loop.mp4` | ROS 2 closed loop on the 2D simulator: the robot steers around potholes (projected ground-truth boxes, not detection) | D093 |
| `5_gazebo_closed_loop.mp4` | Gazebo closed loop, first 230 m: camera → P + B → planner → lane keeper (a stand-in driver) → car. It runs end to end but **does not yet avoid**: 3 of 4 in-lane potholes driven over with the planner, 2 of 4 without | D096, D097 |
| `5b_gazebo_camera_detections.mp4` | Gazebo camera with detections against ground truth (constant command) | D096 |
| `5c_gazebo_camera_lane_keep.mp4` | Gazebo camera with detections, lane-keeping drive | D096 |

Simulated recordings are demonstrations, not field results.
