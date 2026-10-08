# ROS 2 demo (D093)

The drive pipeline as ROS 2 Jazzy nodes around any camera. The corridor, the `Confirmer`
and the state machine run unchanged; ROS is one more `Transport`, and so is CAN: every
decision leaves as a `/cmd_vel` Twist and as a real CAN frame on `vcan0`.

```
sim_node  ─┐                                                          ┌─▶ /cmd_vel (Twist) ─▶ sim_node
video_node ┼─/camera/image_raw─▶ perception_node ─/perception/detections─▶ planner_node ┤
Gazebo cam ┘ /camera/camera_info ──────────────────────────────────────▶ (image size)   └─▶ CAN 0x101 on vcan0
                                                                                               │
                                                     can_monitor_node ◀─────────────────────────┘
                                                       └─▶ /can/decoded (text)
```

| Node | In | Out |
|---|---|---|
| `sim_node` | `/cmd_vel` | `/camera/image_raw`, `/camera/camera_info` (latched), `/sim/ground_truth`, `/sim/pose`, `/sim/path`, `/sim/markers`, `/sim/scenario`, TF `map→base_link→camera_link` |
| `video_node` | `/perception/detections` (lockstep pacing) | `/camera/image_raw`, `/camera/camera_info` (latched, no intrinsics), `/video/frame_info` (`diagnostic_msgs/DiagnosticArray`: video time, counted potholes in view), static TF `map→camera_link` |
| `perception_node` | `/camera/image_raw` from any source; `/sim/ground_truth` and `/video/frame_info` when they have a publisher, paired by stamp | `/perception/detections` (`vision_msgs/Detection2DArray`), `/perception/image_annotated`, `/perception/source` |
| `planner_node` | `/perception/detections`, `/camera/camera_info`, `/video/frame_info` | `/cmd_vel` (`geometry_msgs/Twist`), CAN frames, `/planner/drive_state`, `/planner/markers` |
| `can_monitor_node` | CAN frames on `vcan0` | `/can/decoded` (`std_msgs/String`) |

Every tunable is in [`configs/ros/demo.yaml`](../configs/ros/demo.yaml).

## Run it (Jetson, Ubuntu 24.04, JetPack 7.2)

Once per machine: install ROS 2 Jazzy with `bash ros/install_ros_jazzy.sh` (`ros-jazzy-desktop`, `ros-dev-tools`,
`ros-jazzy-vision-msgs`), then build the project venv on the **system** Python, so that
ROS's `rclpy` loads into it:

```bash
uv venv --system-site-packages --python /usr/bin/python3 .venv
uv sync
```

For CAN, once per boot: `bash ros/install_gazebo_can.sh` creates `vcan0` (needs sudo).

Build the workspace, then source it, in every new terminal:

```bash
source /opt/ros/jazzy/setup.bash && (cd ros && colcon build --packages-select certain_road_ros)
source ros/env.sh
```

### The closed loop: the 2D simulator

```bash
ros2 launch certain_road_ros demo.launch.py
```

Arguments: `source:=projection|detector|auto` (default `projection`, see below),
`scenarios:=centre,left` (a subset, in order), `can:=auto|true|false`, `rviz:=false` (headless).

### A real road video (open loop)

```bash
ros2 launch certain_road_ros video.launch.py
```

Plays the RT Dashcam clip `data/video/2DV-cYmIvT4.mp4` (CC BY) over its ground truth's
window, 120–180 s, through Model P and Model B and the unchanged planner. When the window
ends the launch stops by itself. Arguments:

| Argument | Default | |
|---|---|---|
| `video:=` | `data/video/2DV-cYmIvT4.mp4` | any clip; only this one has ground truth |
| `pacing:=` | `lockstep` | `lockstep`: the next frame waits for the last one's detections, so every frame is processed and 3-of-5 confirmation sees the clip's 30 fps (D075, D088); slower than real time. `realtime`: the wall clock, frames dropped when the GPU falls behind, labelled on screen |
| `start:=` `end:=` | `120` `180` | the window, in video seconds |
| `loop:=` | `false` | play the window again instead of stopping |
| `can:=` | `auto` | `auto` sends CAN when `vcan0` is up, `true` requires it, `false` turns it off |
| `rviz:=` | `true` | |

**A recording cannot be steered.** The planner decides on every frame and its commands
leave as `/cmd_vel` and as CAN frames, but the next frame is the recording's next frame
whatever was decided. The overlay says OPEN LOOP on every frame. The strip above the frame
turns red while one of the 17 hand-counted potholes is in view (`pothole #k of 17`).

### Any other camera (Gazebo)

`perception_node` and `planner_node` work on any `/camera/image_raw` +
`/camera/camera_info` and drive `/cmd_vel`. Without `/sim/ground_truth` the frame is not
waited on, so `source:=auto` (the node's default) runs the detector alone. The planner
reads the image size from `/camera/camera_info`, latched or streamed with every frame;
until one arrives it assumes `configs/sim/robot.yaml`'s 640x640 and logs a warning. The
image subscription is reliable, depth 1: a best-effort camera publisher does not match it.
For a camera that sends no `/sim/scenario`, the staleness failsafe counts frames of
`planner.frame_period_s` (0.1 s). Lockstep video is the one exception: the recording waits
for perception, so no frame is late by the video's clock, and a slow GPU would otherwise
fill the decisions with failsafe STOPs that say nothing about the road. The wall-clock
failsafe is off while lockstep frames arrive, and `video_summary.json` reports perception's
turnaround (median, p99, max) instead.

### Watch the CAN frames

In a second terminal, after `source ros/env.sh`:

```bash
candump vcan0                   # the raw frames: vcan0  101   [4]  01 59 A7 01
ros2 topic echo /can/decoded    # the same frames decoded: 101#0159A701 -> FORWARD speed 0.35 steer -0.70 AUTONOMOUS
```

`can_monitor_node` also logs each decoded frame, and the annotated camera frame shows the
latest one (`CAN 101#...`) beside the drive state, so the demo reads decision → CAN frame
→ decoded. The bus and channel are `configs/ros/demo.yaml`'s `can` block, laid over
`configs/canbus/transport.yaml`, which keeps the Mac's `virtual` default and owns the
arbitration ID (0x101) and the provisional 4-byte layout. On a real bus `vcan0` becomes
`can0`: a config change (D052).

Other views: `rqt_graph` (the nodes and their topics), `ros2 topic hz /cmd_vel` (the
loop's rate), `ros2 topic echo /video/frame_info` (video time and ground truth per frame).

## What a run proves, and what it does not

- **Projection in the 2D sim.** The rendered frames are flat-shaded
  (`certain_road.sim.camera_image`), far from the RDD2022 photos the detectors were
  trained on, and the detectors do not fire on them: with `source:=detector` every
  episode stays NORMAL. So `demo.launch.py` defaults to `source:=projection`
  (`sim.perception_source`): the boxes are `certain_road.sim.project`'s ground truth,
  and the log, `/perception/source` and every frame say **PROJECTION-ONLY**. The 2D sim
  shows the decision loop, not detection.
- **Detector on real video.** `video.launch.py` runs Model P and Model B (weights named in
  `configs/eval/video.yaml`, under the gitignored `runs/kaggle/`); it never falls back to
  projection, since a recording has no simulator ground truth.
- **Per-episode evidence (sim).** `planner_node` writes `runs/ros/<UTC stamp>/episodes.jsonl`:
  for each scenario, whether it reached its `expect` state, and whether its drive-state
  sequence matches `run_scenario` on the same scenario offline. The match is the check
  that ROS added nothing to the decision loop but transport. It also depends on each
  decision reaching the sim before its next 100 ms tick, so a CPU-starved machine can
  show a one-frame divergence while every episode still reaches its state.
- **Per-decision evidence (any camera).** `decisions.jsonl`, one line per decision: state,
  command, CAN payload, and for a video frame its video time and the counted potholes in
  view. `can_frames.jsonl` is what `can_monitor_node` read back off the bus.
- **Video evidence.** `video_summary.json` (frames sent, processed, dropped; fps; real-time
  factor) and `video_score.json` (`certain_road_ros.video.score_decisions`): which of the
  17 counted potholes the planner left NORMAL for, and how many reaction and manoeuvre
  onsets began with no counted pothole in view. The ground truth is one annotator's
  intervals with no boxes, so a reaction while a pothole is in view may be to something
  else: an upper bound, as in `scripts/score_video_gt.py`.
- **D050's limits still apply:** no motion blur, vibration, lighting, real command latency
  or actuator dynamics in the 2D sim, and no closed loop at all on video.

## Tests

`tests/test_ros_package.py` runs only where ROS is sourced and is skipped in CI.
`tests/test_ros_video.py` (ground truth, frame facts, the decisions' score) and
`tests/test_ros_can.py` (fan-out, config override, the byte path over python-can's
`virtual` bus, and over `vcan0` where it exists) import no ROS and run anywhere. With ROS
sourced, one of the pytest plugins ROS installs auto-loads and stalls the run, so:

```bash
source ros/env.sh
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python -m pytest tests/test_ros_package.py tests/test_ros_video.py tests/test_ros_can.py
```
