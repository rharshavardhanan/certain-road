"""The whole demo: `ros2 launch certain_road_ros demo.launch.py` (D093).

Starts sim_node, perception_node, planner_node, can_monitor_node and RViz. Arguments:

    source:=projection|detector|auto   perception input (default: configs/ros/demo.yaml
                                       sim.perception_source, projection: the detectors
                                       do not fire on the flat-shaded renders)
    scenarios:=centre,left             a subset of the trial matrix, in this order
    can:=auto|true|false               each decision also as a CAN frame (vcan0); auto
                                       sends when the bus is up
    rviz:=false                        headless, e.g. over SSH
"""

from datetime import UTC, datetime
from pathlib import Path

import yaml
from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument
from launch.conditions import IfCondition
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node
from launch_ros.parameter_descriptions import ParameterValue

PACKAGE = "certain_road_ros"


def _sim_source() -> str:
    """configs/ros/demo.yaml's sim.perception_source. `ros2 launch` runs on the system
    Python, which cannot import certain_road, so the repository is found as
    `certain_road.core.paths.repo_root` finds it: the launch file is installed under ros/."""
    for root in Path(__file__).resolve().parents:
        if (root / "pyproject.toml").exists():
            cfg = yaml.safe_load((root / "configs" / "ros" / "demo.yaml").read_text())
            return cfg["sim"]["perception_source"]
    raise RuntimeError("repository root not found above this launch file")


def _text(name: str) -> ParameterValue:
    """A string parameter even when empty; unpinned, "" would be read as YAML null."""
    return ParameterValue(LaunchConfiguration(name), value_type=str)


def generate_launch_description() -> LaunchDescription:
    rviz_config = Path(get_package_share_directory(PACKAGE)) / "rviz" / "demo.rviz"
    run_stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")  # one runs/ros/ folder per launch
    return LaunchDescription(
        [
            DeclareLaunchArgument(
                "source", default_value=_sim_source(), description="projection|detector|auto"
            ),
            DeclareLaunchArgument("scenarios", default_value="", description="comma-separated"),
            DeclareLaunchArgument("can", default_value="", description="auto|true|false"),
            DeclareLaunchArgument("rviz", default_value="true"),
            Node(
                package=PACKAGE,
                executable="sim_node",
                output="screen",
                parameters=[{"scenarios": _text("scenarios")}],
            ),
            Node(
                package=PACKAGE,
                executable="perception_node",
                output="screen",
                parameters=[{"source": _text("source")}],
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
        ]
    )
