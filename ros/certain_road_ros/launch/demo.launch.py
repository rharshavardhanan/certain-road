"""The whole demo: `ros2 launch certain_road_ros demo.launch.py` (D093).

Starts sim_node, perception_node, planner_node and RViz. Arguments:

    source:=auto|detector|projection   perception input (default: configs/ros/demo.yaml)
    scenarios:=centre,left             a subset of the trial matrix, in this order
    rviz:=false                        headless, e.g. over SSH
"""

from pathlib import Path

from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument
from launch.conditions import IfCondition
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node
from launch_ros.parameter_descriptions import ParameterValue

PACKAGE = "certain_road_ros"


def _text(name: str) -> ParameterValue:
    """A string parameter even when empty; unpinned, "" would be read as YAML null."""
    return ParameterValue(LaunchConfiguration(name), value_type=str)


def generate_launch_description() -> LaunchDescription:
    rviz_config = Path(get_package_share_directory(PACKAGE)) / "rviz" / "demo.rviz"
    return LaunchDescription(
        [
            DeclareLaunchArgument(
                "source", default_value="", description="auto|detector|projection"
            ),
            DeclareLaunchArgument("scenarios", default_value="", description="comma-separated"),
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
            Node(package=PACKAGE, executable="planner_node", output="screen"),
            Node(
                package="rviz2",
                executable="rviz2",
                arguments=["-d", str(rviz_config)],
                condition=IfCondition(LaunchConfiguration("rviz")),
            ),
        ]
    )
