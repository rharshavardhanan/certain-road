"""Gazebo Harmonic world for certain-road: the exported road, the camera car, the ROS bridge.

    ros2 launch certain_road_gz world.launch.py preset:=poor seed:=0
    ros2 launch certain_road_gz world.launch.py world:=/data/worlds/poor_seed0 \
        cam_w:=640 cam_h:=360 cam_hz:=15 headless:=false

Starts Gazebo, spawns the car, and runs the bridge and the camera's static transforms. No
detector, planner or CAN node runs here, so this can run on a separate simulation PC while
the Jetson runs the models over the network. The bridge publishes /clock, and every node here
runs on it (use_sim_time), as must every node that follows the simulation, on any machine.

Arguments:
  world        exported world folder (or its world.sdf). Default: <worlds_dir>/<preset>_seed<seed>
  worlds_dir   default $CERTAIN_ROAD_GZ_WORLDS, else runs/gazebo under the working directory
  preset, seed the road (poor, 0)
  headless     true: server only, offscreen (EGL) rendering; false: with the Gazebo window
  cam_w, cam_h, cam_hz   camera resolution and rate; empty keeps the car's (1280x720, 30 Hz).
               config/car.yaml's camera_low (640x360, 15 Hz) suits a network link.
  bridge       false: Gazebo and the car only
  rtf          real-time factor to run at (e.g. 0.3, so a slow consumer sees every frame of
               simulated time); empty keeps the world's (1.0). Set through gz-sim's
               set_physics service once the world is up; the SDF is not changed
  use_sim_time default true
  verbosity    gz sim -v level
"""

import tempfile
from pathlib import Path

import yaml
from ament_index_python.packages import get_package_share_directory
from certain_road_gz import launch_args
from launch import LaunchDescription
from launch.actions import (
    DeclareLaunchArgument,
    EmitEvent,
    ExecuteProcess,
    LogInfo,
    OpaqueFunction,
    RegisterEventHandler,
)
from launch.event_handlers import OnProcessExit
from launch.events import Shutdown
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node

PACKAGE = "certain_road_gz"
# set_physics is retried until the world answers: loading the road takes 15-25 s on the Jetson
SET_PHYSICS_TRIES = 60
SET_PHYSICS_WAIT_S = 2.0
ARGS = {
    "world": ("", "exported world folder or its world.sdf"),
    "worlds_dir": ("", "folder of exported worlds"),
    "preset": ("poor", "road preset, when world is not given"),
    "seed": ("0", "road seed, when world is not given"),
    "headless": ("true", "server only, offscreen rendering"),
    "cam_w": ("", "camera width in px; empty keeps the car's"),
    "cam_h": ("", "camera height in px; empty keeps the car's"),
    "cam_hz": ("", "camera rate in Hz; empty keeps the car's"),
    "bridge": ("true", "run the ros_gz bridge"),
    "rtf": ("", "real-time factor; empty keeps the world's"),
    "use_sim_time": ("true", "follow /clock"),
    "verbosity": ("2", "gz sim verbosity, 0-4"),
}


def _setup(context):
    arg = {k: LaunchConfiguration(k).perform(context) for k in ARGS}
    share = Path(get_package_share_directory(PACKAGE))
    car = yaml.safe_load((share / "config/car.yaml").read_text())
    folder = launch_args.world_dir(
        arg["world"], arg["worlds_dir"], arg["preset"], arg["seed"], Path.cwd()
    )
    meta = launch_args.world_meta(folder)
    sdf = launch_args.with_camera(
        (share / car["model_sdf"]).read_text(), arg["cam_w"], arg["cam_h"], arg["cam_hz"]
    )
    car_file = Path(tempfile.mkdtemp(prefix="certain_road_gz_")) / "car.sdf"
    car_file.write_text(sdf)
    cam = launch_args.camera_settings(sdf)
    sim_time = arg["use_sim_time"].lower() == "true"
    headless = arg["headless"].lower() == "true"
    gz = ["gz", "sim", "-r", "-v", arg["verbosity"]]
    gz += ["-s", "--headless-rendering"] if headless else []
    gz_sim = ExecuteProcess(
        cmd=[*gz, str(folder / meta["world_sdf"])], name="gz_sim", output="screen"
    )
    actions = [
        LogInfo(
            msg=f"world {folder} ({meta['preset']} seed {meta['seed']}); camera "
            f"{cam['w']}x{cam['h']} at {cam['rate_hz']:g} Hz; headless {headless}"
        ),
        gz_sim,
        RegisterEventHandler(
            OnProcessExit(target_action=gz_sim, on_exit=[EmitEvent(event=Shutdown())])
        ),
        Node(
            package="ros_gz_sim",
            executable="create",
            arguments=launch_args.spawn_args(meta, car, car_file),
            parameters=[{"use_sim_time": sim_time}],
            output="screen",
        ),
    ]
    if arg["rtf"]:
        world_sdf = folder / meta["world_sdf"]
        script = launch_args.set_physics_script(
            meta["world_name"],
            launch_args.physics_step(world_sdf),
            float(arg["rtf"]),
            SET_PHYSICS_TRIES,
            SET_PHYSICS_WAIT_S,
        )
        actions.append(ExecuteProcess(cmd=["bash", "-c", script], name="set_rtf", output="screen"))
    for i, tf in enumerate(launch_args.static_tf_args(car)):
        actions.append(
            Node(
                package="tf2_ros",
                executable="static_transform_publisher",
                name=f"camera_tf_{i}",
                arguments=tf,
                parameters=[{"use_sim_time": sim_time}],
            )
        )
    if arg["bridge"].lower() == "true":
        actions.append(
            Node(
                package="ros_gz_bridge",
                executable="parameter_bridge",
                name="gz_bridge",
                parameters=[
                    {"config_file": str(share / "config/bridge.yaml"), "use_sim_time": sim_time}
                ],
                output="screen",
            )
        )
    return actions


def generate_launch_description():
    return LaunchDescription(
        [DeclareLaunchArgument(k, default_value=d, description=h) for k, (d, h) in ARGS.items()]
        + [OpaqueFunction(function=_setup)]
    )
