"""A real road video into the drive graph: `ros2 launch certain_road_ros video.launch.py`.

Starts video_node, perception_node (Model P + Model B, detector only), planner_node,
can_monitor_node and RViz. OPEN LOOP: a recording cannot be steered, so the planner's
decisions are made, logged, sent as /cmd_vel and as CAN frames, and change nothing on
screen. Arguments:

    video:=data/video/2DV-cYmIvT4.mp4  the clip (default: configs/ros/demo.yaml video.clip)
    pacing:=lockstep|realtime          every frame processed (default), or the wall clock
                                       with frames dropped when the GPU falls behind
    start:=120 end:=180                window in video seconds (default: the ground truth's)
    loop:=false                        at the window's end stop everything, or play again
    can:=auto|true|false               each decision also as a CAN frame (vcan0); auto
                                       sends when the bus is up
    rviz:=false                        headless, e.g. over SSH

When video_node finishes the window the whole launch stops; the planner then writes
runs/ros/<stamp>/video_score.json beside decisions.jsonl, video_summary.json and
can_frames.jsonl.
"""

from datetime import UTC, datetime
from pathlib import Path

from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, EmitEvent, RegisterEventHandler
from launch.conditions import IfCondition
from launch.event_handlers import OnProcessExit
from launch.events import Shutdown
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node
from launch_ros.parameter_descriptions import ParameterValue

PACKAGE = "certain_road_ros"


def _text(name: str) -> ParameterValue:
    """A string parameter even when empty or numeric; unpinned, "" would be YAML null."""
    return ParameterValue(LaunchConfiguration(name), value_type=str)


def generate_launch_description() -> LaunchDescription:
    rviz_config = Path(get_package_share_directory(PACKAGE)) / "rviz" / "video.rviz"
    run_stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")  # one runs/ros/ folder per launch
    video = Node(
        package=PACKAGE,
        executable="video_node",
        output="screen",
        parameters=[
            {
                "video": _text("video"),
                "pacing": _text("pacing"),
                "start": _text("start"),
                "end": _text("end"),
                "loop": _text("loop"),
                "run_stamp": run_stamp,
            }
        ],
    )
    return LaunchDescription(
        [
            DeclareLaunchArgument("video", default_value="", description="path to the clip"),
            DeclareLaunchArgument("pacing", default_value="", description="lockstep|realtime"),
            DeclareLaunchArgument("start", default_value="", description="window start, s"),
            DeclareLaunchArgument("end", default_value="", description="window end, s"),
            DeclareLaunchArgument("loop", default_value="", description="true|false"),
            DeclareLaunchArgument("can", default_value="", description="auto|true|false"),
            DeclareLaunchArgument("rviz", default_value="true"),
            video,
            Node(
                package=PACKAGE,
                executable="perception_node",
                output="screen",
                # a recording has no simulator ground truth to project: the models or nothing
                parameters=[{"source": "detector"}],
            ),
            Node(
                package=PACKAGE,
                executable="planner_node",
                output="screen",
                parameters=[{"can": _text("can"), "run_stamp": run_stamp}],
            ),
            Node(
                package=PACKAGE,
                executable="can_monitor_node",
                output="screen",
                parameters=[{"can": _text("can"), "run_stamp": run_stamp}],
            ),
            Node(
                package="rviz2",
                executable="rviz2",
                arguments=["-d", str(rviz_config)],
                condition=IfCondition(LaunchConfiguration("rviz")),
            ),
            RegisterEventHandler(
                OnProcessExit(
                    target_action=video,
                    on_exit=[EmitEvent(event=Shutdown(reason="video window done"))],
                )
            ),
        ]
    )
