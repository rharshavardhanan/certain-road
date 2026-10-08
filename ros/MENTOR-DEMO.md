# Mentor demo: what to show, in what order, and what to say

## Review day: start here

1. Power on the Jetson, log in, open a terminal: `cd ~/certain-road`
2. `bash ros/review_preflight.sh`: every line should say OK (about 5 s, no GPU). If
   `vcan0` fails, run `bash ros/install_gazebo_can.sh` once (sudo).
3. Show the parts below in order. Every part has a recording that plays at real speed;
   play it if the live run is slow or anything misbehaves. In each new terminal, run
   `source ros/env.sh` first.

| # | Part | Live command | Recording |
|---|---|---|---|
| 1 | MuJoCo road simulation | `bash ros/demos/1_mujoco_survey.sh [good|moderate|poor]` | `runs/demo_capture/mujoco_poor_seed0.mp4` |
| 2 | Real road video, P + B live | `bash ros/demos/2_real_road_live.sh` | `runs/demo_capture/real_road_120-180s.mp4` |
| 3 | Real road through ROS, decisions as CAN frames | `bash ros/demos/3_ros_video_can.sh` (opens a CAN window) | `runs/ros/capture/video_rviz_*.mp4` |
| 4 | ROS 2D closed loop | `bash ros/demos/4_ros_2d_loop.sh` | `runs/ros/capture/demo_*.mp4` |
| 5 | Gazebo: realistic 3D road, car with suspension, closed loop | `bash ros/demos/5_gazebo_closed_loop.sh [noon|morning|evening|overcast]` (opens a CAN window) | `runs/ros/capture/gazebo_closed_loop_*.mp4` |
| 6 | Survey report: three roads, vision-estimated PCI, road lifespan, priority, frames | `bash ros/demos/6_survey_report.sh` | (the report is the artefact) |

**What parts 3, 5 and 6 add, and their honest status (2026-10-08):**

- **Part 3** (D095): the real clip streamed as a ROS camera; every decision also leaves as a
  CAN frame on `vcan0` (ID 0x101, 4 bytes: action, speed, signed steer, mode; a provisional
  layout). 1800 frames → 1800 decisions → 1800 CAN frames, decoded byte for byte. The
  planner reacted during 12 of the 17 counted potholes; 27 of its 53 manoeuvre onsets had no
  counted pothole in view, and manoeuvres flicker (median 2 frames). Open loop: a recording
  cannot be steered.
- **Part 5** (D096, D097): the Gazebo world is the MuJoCo road converted to meshes; Model P
  boxed 23 of the 28 potholes that came into view, and a wheel crossing a pothole moves the
  body up to 11.7 mm, 0.68° pitch. The closed loop runs (camera → P + B → planner → lane
  keeper → car, CAN on). **Measured over the first 230 m, it does not avoid potholes yet:** with the planner the
  wheels went over 3 of the 4 in-lane potholes, without it (lane keeper only) 2 of 4; its
  left swerves put a wheel into pothole #25, and it began 26 swerves, mostly at nothing.
  CAN works in the loop: 1,371 decisions, 1,371 frames decoded. Say this plainly: the
  pipeline runs end to end, and the measurement shows what needs tuning next (D097). The lane keeper is a stand-in driver,
  not under test. Gazebo runs at 0.3x real time here so perception sees every frame.
- **Part 6** (D098): road lifespan uses Sharaf, Reichelt, Shahin and Sinha (1987, TRR 1123),
  a US PAVER model, **pending your approval**: no Indian PCI–age model could be verified.
  The alternative is `mode: pci_only` in `configs/rsl/published_default.yaml`. Ask the
  mentor which they want.

---

The original three-part plan follows; its numbers still hold.

Everything here runs on the Jetson Orin Nano (JetPack 7.2, CUDA), measured on 2026-10-08.
About 8 minutes in three parts. Each part answers a different question.

| # | Part | The question it answers | Recording (real speed) | Length |
|---|---|---|---|---|
| 1 | MuJoCo road simulation | Do the trained models and the whole pipeline work, against exact ground truth? | `runs/demo_capture/mujoco_poor_seed0.mp4` | 1 min 42 s |
| 2 | Real Indian road video | Do the models work on a real road, not only a simulated one? | `runs/demo_capture/real_road_120-180s.mp4` | 1 min 8 s |
| 3 | ROS 2 closed loop | Does a decision actually change what the vehicle does? | `runs/ros/capture/demo_20261006T110324Z.mp4` | 1 min 6 s |

**Play the recordings as the main flow**, then run one part live to prove it runs on the
Jetson. Live, every frame goes through both models and none is skipped, because the 3-of-5
confirmation rule breaks when frames are dropped (D088). So the live views run slower than
real time: MuJoCo at about 0.2x, the real road at about 0.4x. The recordings play at the
true speed.

---

## Part 1: the MuJoCo road simulation (the main demo)

**What is on screen.** One 1920x1080 screen, four panels:

- **Camera:** what the models see. Model P boxes potholes (red), Model B boxes cracks
  (orange, yellow); a box turns **green** once the same track is seen in 3 of 5 frames.
  The outlined strip is the 5 m survey sample.
- **Survey map:** the road in plan, and a vision-estimated PCI per 50 m segment.
- **Survey counts:** confirmed potholes (Model P) and cracks (Model B).
- **Drift monitor:** whether the road looks unlike the data Model B was trained on.

It ends on a **result screen**: each segment's vision-estimated PCI next to the reference
PCI, the two repair plans, and detection scored against the exact ground truth.

**What to say:** "The road is generated, so the ground truth is exact. The surface is built
from real CC BY photos of Indian potholes and cracks at real-world sizes, with 3D potholes,
shadows and motion blur. Everything that detects, confirms, scores and plans is the
project's real code and trained models."

**The numbers it shows** (poor road, seed 0, on the Jetson):

| | Caught | False alarms |
|---|---|---|
| Potholes (Model P) | 16 of 28 (57%) | 44.9 per km |
| Alligator cracks (Model B) | 21 of 24 (88%) | 9.8 per km |
| Linear cracks (Model B) | 14 of 27 (52%) | 0 |

Repair plans at a 30% budget: the optimiser covers 1 of the true worst 3 segments,
worst-first covers 2 of 3, both with a true benefit of 58. The drift alarm fires at 345 m.

The Mac run of the same road (`docs/mujoco-demo.md`) got potholes 15/28, alligator 21/24,
linear 15/27, and no drift alarm. Close, not identical: the textures on the Jetson were
rebuilt from the public datasets (not byte-identical), and the GPU arithmetic differs.

**Run it live** (the scene build takes about 3.5 minutes, so start it before you need it):

```bash
cd ~/certain-road
.venv/bin/python -m sim.mujoco.demo --preset poor --seed 0
# Esc or q stops early; the result screen stays until a key is pressed
```

---

## Part 2: the real road video

**What is on screen.** The RT Dashcam clip of a real Indian road (YouTube `2DV-cYmIvT4`,
CC BY), 120–180 s, with Model P and Model B running on every frame:

- boxes in class colours, **green** once confirmed (the same rule as Part 1)
- the dashed horizon gate: boxes above it are ignored
- a strip that turns **red while one of the 17 hand-counted potholes is in view**
- a live tally of counted potholes passed and caught by Model P

**What to say:** "This is not simulated. The models have never seen this video."

**The numbers it shows:** Model P caught **12 of the 17** counted potholes, with **21 false
alarms per minute**. Model B confirmed 6 crack tracks. The repo's earlier run on the Mac got
10 of 17 and 20 per minute.

**Say these limits before you are asked:**

- **Open loop.** A recording cannot be steered. The models detect; nothing drives.
- **The ground truth is one annotator,** an AI pass over the raw video (see the CSV header in
  `configs/eval/gt/`), counted as time intervals, not boxes. A track counts as a catch if it
  overlaps a pothole's interval in time, so catches are an upper bound.
- **Many false alarms.** Model P fires about once every three seconds on this road. That is
  why the drive pipeline confirms over 3 of 5 frames, and why the survey reports intervals,
  not single detections.

**Run it live** (starts in seconds):

```bash
cd ~/certain-road
.venv/bin/python scripts/live_video.py data/video/2DV-cYmIvT4.mp4
# q or Esc stops; the final score is printed and saved to runs/video_live/
```

---

## Part 3: the ROS 2 closed loop

**What is on screen.** RViz: a robot drives the trial-matrix scenarios and steers around
potholes; the camera panel shows the boxes, the planner's corridor and its decision; above
the robot, NORMAL / WARNING / AVOID_LEFT / AVOID_RIGHT / STOP. Open `rqt_graph` beside it:
`sim_node → perception_node → planner_node → sim_node`.

**What to say:** "The drive decision code runs unchanged; ROS is one more transport for its
commands. Every episode reached its expected state and matched the offline simulator frame
for frame."

**Say this limit:** this part uses a flat-shaded 2D simulator and the simulator's own
ground-truth boxes (PROJECTION-ONLY, as the screen says), because a recording cannot be
steered and the photographic MuJoCo road drives straight. It shows the decision loop, not
detection.

**Run it live:**

```bash
cd ~/certain-road && source ros/env.sh
ros2 launch certain_road_ros demo.launch.py
# second terminal: source ros/env.sh && rqt_graph
```

---

## Questions you are likely to get

| Question | Honest answer |
|---|---|
| Why is it slower than real time on the Jetson? | Two YOLOv8s models run in full-precision PyTorch on an Orin Nano, about 30 ms each per frame, plus rendering. Exporting them to TensorRT at FP16 is the usual next step; it has not been done or measured |
| Why so many pothole false alarms? | In the simulation they sit on crack patches (D092); on the real road the detector fires on dark, broken surface. Confirmation over frames and survey sampling are the mitigation; the rate is reported, not hidden |
| Why not Gazebo or CARLA? | Decided in D050: setup cost and GPU needs; the 2D simulator exercises the same decision code |
| Is the simulation the real world? | No. The result screen says so: "a demonstration, not a field result". Part 2 is the real-world evidence |

---

## Setup done on the Jetson (2026-10-08)

| Needed | Where it came from |
|---|---|
| Model P and B weights | Kaggle kernel output (`harshavardhananr/roadsight-train-p`, `-b`). SHA-256 matches `results/LOCKED/P_india_heldout.json` and `B_india_heldout.json` |
| Real road video | YouTube via `yt-dlp`, 1280x720, 30 fps, 290.9 s, the same as the repo's recorded metadata |
| 49 MuJoCo textures | Rebuilt from the public datasets with `scripts/fetch_trial_textures.py`: QR4Change from Mendeley (SHA-256 checked), BD-N6 from the Zenodo zips by range request, resized to `docs/texture-provenance.md`'s sizes |
| Drift reference image list | `data/yolo/india_val.txt`, copied from the identical committed `splits/india_val.txt` |

Code changes that made the repo run here (D094): the configs' `mps` device now resolves to
`cuda` on a machine without MPS (`certain_road/core/device.py`); the screen fonts fall back
from the Mac's to DejaVu; `scripts/live_video.py` is new.

Known cosmetic flaws in the recordings: stacked boxes overlap their labels, and the mp4
codec leaves faint ghosting where on-screen text changes.

All stills are in `runs/demo_capture/`: `mujoco_poor_seed0_last.png` (the live screen),
`mujoco_poor_seed0_end.png` (the result screen), `real_road_frame.png`.
