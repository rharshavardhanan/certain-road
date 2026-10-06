# ROS 2 demo (D093)

The drive pipeline as three ROS 2 Jazzy nodes around the 2D simulator. The corridor,
the `Confirmer` and the state machine run unchanged; ROS is one more `Transport`.

```
sim_node ──/camera/image_raw──▶ perception_node ──/perception/detections──▶ planner_node
   ▲      ──/sim/ground_truth─▶                                                  │
   └──────────────────────────────────── /cmd_vel (Twist) ◀──── RosTransport ◀───┘
```

| Node | In | Out |
|---|---|---|
| `sim_node` | `/cmd_vel` | `/camera/image_raw`, `/sim/ground_truth`, `/sim/pose`, `/sim/path`, `/sim/markers`, `/sim/scenario`, TF `map→base_link→camera_link` |
| `perception_node` | image + ground truth, paired by stamp | `/perception/detections` (`vision_msgs/Detection2DArray`), `/perception/image_annotated`, `/perception/source` |
| `planner_node` | `/perception/detections` | `/cmd_vel` (`geometry_msgs/Twist`), `/planner/drive_state`, `/planner/markers` |

Every tunable is in [`configs/ros/demo.yaml`](../configs/ros/demo.yaml).

## Run it (Jetson, Ubuntu 24.04, JetPack 7.2)

Once per machine: install ROS 2 Jazzy with `bash ros/install_ros_jazzy.sh` (`ros-jazzy-desktop`, `ros-dev-tools`,
`ros-jazzy-vision-msgs`), then build the project venv on the **system** Python, so that
ROS's `rclpy` loads into it:

```bash
uv venv --system-site-packages --python /usr/bin/python3 .venv
uv sync
```

Build the workspace, then source it, in every new terminal:

```bash
source /opt/ros/jazzy/setup.bash && (cd ros && colcon build)
source ros/env.sh
ros2 launch certain_road_ros demo.launch.py
```

Arguments: `source:=auto|detector|projection`, `scenarios:=centre,left` (a subset, in
order), `rviz:=false` (headless). In a second terminal, after `source ros/env.sh`:

```bash
rqt_graph                       # the three nodes and their topics
ros2 topic hz /cmd_vel          # the loop's rate
```

## What a run proves, and what it does not

- **Detector or projection.** `auto` uses Model P and Model B if torch, ultralytics
  and both weights files load (`configs/eval/video.yaml` names them, under the gitignored
  `runs/kaggle/`). Otherwise the boxes are `certain_road.sim.project`'s ground truth,
  and the log, `/perception/source` and every frame say **PROJECTION-ONLY**.
- **Rendered frames are not photographs.** The camera frame is flat-shaded
  (`certain_road.sim.camera_image`), far from the RDD2022 photos the detectors were
  trained on. A detector missing these potholes says nothing about real roads.
- **Per-episode evidence.** `planner_node` writes `runs/ros/<UTC stamp>/episodes.jsonl`:
  for each scenario, whether it reached its `expect` state, and whether its drive-state
  sequence matches `run_scenario` on the same scenario offline. The match is the check
  that ROS added nothing to the decision loop but transport.
- **D050's limits still apply:** no motion blur, vibration, lighting, real command
  latency or actuator dynamics.

## Tests

`tests/test_ros_package.py` runs only where ROS is sourced and is skipped in CI. With ROS
sourced, one of the pytest plugins ROS installs auto-loads and stalls the run, so:

```bash
source ros/env.sh
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python -m pytest tests/test_ros_package.py
```
