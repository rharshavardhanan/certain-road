"""The closed loop in Gazebo: `ros2 launch certain_road_ros gazebo.launch.py` (D093, sim/gazebo).

Camera -> Model P + Model B -> planner -> /cmd_vel -> the car, every decision also a CAN
frame on vcan0. Starts:

- the world (certain_road_gz world.launch.py): the exported road, the car, the bridge, run
  at `rtf` so perception sees every 30 Hz frame of simulated time (D088's premise);
- perception_node, detector only, drawing the car corridor;
- planner_node with the car's profile and corridor (configs/sim/car.yaml,
  configs/driving/corridor_car.yaml), CAN on, its /cmd_vel remapped to /planner/cmd_vel;
- lane_keeper_node, the STAND-IN DRIVER (not under test): holds the lane while the planner
  is NORMAL or WARNING, passes the planner's Twist in AVOID and STOP, sends the car's
  /cmd_vel at the planner's speed;
- can_monitor_node, road_markers_node (ground truth and the car's track for RViz), and RViz.

Every node runs on /clock (use_sim_time). Arguments:

    preset:=poor seed:=0       the exported world runs/gazebo/<preset>_seed<seed> (or world:=)
    rtf:=0.3                   Gazebo's real-time factor (rtf:=1.0 is the world's own; ros2
                               launch rejects an empty rtf:=)
    planner:=true              false: the baseline, no perception or planner; the stand-in
                               drives the cruise speed and holds the lane, reacting to nothing
    gazebo:=true               false: the world runs elsewhere (another PC on this ROS domain)
    can:=auto|true|false       as demo.launch.py
    rviz:=false                camera + top-down layout
    headless:=true             Gazebo without its own window
    cam_w:= cam_h:= cam_hz:=   camera override (empty: the car's 1280x720 at 30 Hz)

Logs go to runs/ros/<UTC stamp>/: decisions.jsonl (planner), can_frames.jsonl
(can_monitor_node), lane_keeper.json (the stand-in's share of the steering). Run
sim/gazebo/closed_loop.py on them to score the run against the road's ground truth.
"""

import json
from datetime import UTC, datetime
from pathlib import Path

import yaml
from ament_index_python.packages import get_package_share_directory
from certain_road_gz import launch_args
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, IncludeLaunchDescription, OpaqueFunction
from launch.launch_description_sources import PythonLaunchDescriptionSource
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node

PACKAGE = "certain_road_ros"
ARGS = {
    "preset": ("poor", "road preset"),
    "seed": ("0", "road seed"),
    "world": ("", "exported world folder (overrides preset and seed)"),
    "rtf": ("0.3", "Gazebo real-time factor, e.g. 0.3; 1.0 is the world's own"),
    "planner": ("true", "false: lane-keep-only baseline, no perception or planner"),
    "gazebo": ("true", "false: the world runs on another machine"),
    "can": ("", "auto|true|false"),
    "rviz": ("false", "camera + top-down RViz"),
    "headless": ("true", "Gazebo without its window"),
    "cam_w": ("", "camera width"),
    "cam_h": ("", "camera height"),
    "cam_hz": ("", "camera rate"),
}


def _repo() -> Path:
    """The repository, found as demo.launch.py finds it: the launch file is installed under ros/."""
    for root in Path(__file__).resolve().parents:
        if (root / "pyproject.toml").exists():
            return root
    raise RuntimeError("repository root not found above this launch file")


def _setup(context):
    arg = {k: LaunchConfiguration(k).perform(context) for k in ARGS}
    repo = _repo()
    demo = yaml.safe_load((repo / "configs/ros/demo.yaml").read_text())
    gz_share = Path(get_package_share_directory("certain_road_gz"))
    car = yaml.safe_load((gz_share / "config/car.yaml").read_text())
    folder = launch_args.world_dir(arg["world"], "", arg["preset"], arg["seed"], repo)
    meta = launch_args.world_meta(folder)
    cam_hz = float(arg["cam_hz"] or car["camera_default"]["rate_hz"])
    planner = arg["planner"].lower() == "true"
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    sim = {"use_sim_time": True}
    vehicle = "car"
    actions = []
    if arg["gazebo"].lower() == "true":
        actions.append(
            IncludeLaunchDescription(
                PythonLaunchDescriptionSource(str(gz_share / "launch/world.launch.py")),
                launch_arguments={
                    "world": str(folder),
                    "rtf": arg["rtf"],
                    "headless": arg["headless"],
                    "cam_w": arg["cam_w"],
                    "cam_h": arg["cam_h"],
                    "cam_hz": arg["cam_hz"],
                }.items(),
            )
        )
    if planner:
        actions += [
            Node(
                package=PACKAGE,
                executable="perception_node",
                output="screen",
                parameters=[{"source": "detector", "vehicle": vehicle, **sim}],
            ),
            Node(
                package=PACKAGE,
                executable="planner_node",
                output="screen",
                parameters=[
                    {
                        "vehicle": vehicle,
                        "can": arg["can"],
                        "run_stamp": stamp,
                        # the staleness failsafe counts the camera's frames, 1/30 s
                        "frame_period_s": 1.0 / cam_hz,
                        **sim,
                    }
                ],
                remappings=[(demo["topics"]["cmd_vel"], demo["topics"]["planner_cmd_vel"])],
            ),
            Node(
                package=PACKAGE,
                executable="can_monitor_node",
                output="screen",
                parameters=[{"can": arg["can"], "run_stamp": stamp, "vehicle": vehicle, **sim}],
            ),
        ]
    actions += [
        Node(
            package=PACKAGE,
            executable="lane_keeper_node",
            output="screen",
            parameters=[
                {
                    "lane_y": float(meta["spawn"]["y"]),
                    "alone": not planner,
                    "vehicle": vehicle,
                    "run_stamp": stamp,
                    **sim,
                }
            ],
        ),
        Node(
            package=PACKAGE,
            executable="road_markers_node",
            output="screen",
            parameters=[{"world": str(folder), **sim}],
        ),
    ]
    if arg["rviz"].lower() == "true":
        rviz = Path(get_package_share_directory(PACKAGE)) / "rviz" / "gazebo.rviz"
        actions.append(
            Node(package="rviz2", executable="rviz2", arguments=["-d", str(rviz)], parameters=[sim])
        )
    (repo / demo["planner"]["log_dir"] / stamp).mkdir(parents=True, exist_ok=True)
    (repo / demo["planner"]["log_dir"] / stamp / "launch.json").write_text(
        json.dumps({"args": arg, "world": str(folder), "cam_hz": cam_hz}, indent=1)
    )
    return actions


def generate_launch_description() -> LaunchDescription:
    return LaunchDescription(
        [DeclareLaunchArgument(k, default_value=d, description=h) for k, (d, h) in ARGS.items()]
        + [OpaqueFunction(function=_setup)]
    )
