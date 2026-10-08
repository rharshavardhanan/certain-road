"""The ROS survey: `ros2 launch certain_road_survey survey.launch.py`.

Starts survey_node only. Run it beside a camera source and perception, for example the
Gazebo world (certain_road_gz world.launch.py) and certain_road_ros's perception_node, then
drive. Arguments:

    label:="Gazebo road"     the road's name on the report (default: configs/report/ros_survey.yaml)
    chainage:=world_x|path   world_x for a road laid along x from 0 (the Gazebo world), path for
                             any other road
    simulated:=true          a simulator camera: the report carries the demonstration caption
    use_sim_time:=true       follow /clock (Gazebo); false for a real camera

Writes runs/ros_survey/<stamp>/report.html each time a segment closes and on shutdown. Stop with
Ctrl-C (or SIGTERM to the launch). `ros2 run` does not pass SIGTERM on to the node: under
`ros2 run`, stop with Ctrl-C or signal the survey_node process itself.
"""

from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node
from launch_ros.parameter_descriptions import ParameterValue

ARGS = {
    "label": ("Gazebo road", "the road's name on the report"),
    "chainage": ("world_x", "world_x or path"),
    "simulated": ("true", "the camera is a simulator's"),
    "use_sim_time": ("true", "follow /clock"),
}


def generate_launch_description() -> LaunchDescription:
    survey = Node(
        package="certain_road_survey",
        executable="survey_node",
        output="screen",
        parameters=[
            {
                "label": ParameterValue(LaunchConfiguration("label"), value_type=str),
                "chainage": ParameterValue(LaunchConfiguration("chainage"), value_type=str),
                "simulated": ParameterValue(LaunchConfiguration("simulated"), value_type=bool),
                "use_sim_time": ParameterValue(
                    LaunchConfiguration("use_sim_time"), value_type=bool
                ),
            }
        ],
    )
    return LaunchDescription(
        [DeclareLaunchArgument(k, default_value=d, description=h) for k, (d, h) in ARGS.items()]
        + [survey]
    )
