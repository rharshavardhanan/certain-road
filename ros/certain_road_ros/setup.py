"""ament_python package for the ROS 2 demo (D093). Built by `colcon build` from ros/."""

from glob import glob

from setuptools import setup

PACKAGE = "certain_road_ros"

setup(
    name=PACKAGE,
    version="0.1.0",
    packages=[PACKAGE],
    data_files=[
        ("share/ament_index/resource_index/packages", [f"resource/{PACKAGE}"]),
        (f"share/{PACKAGE}", ["package.xml"]),
        (f"share/{PACKAGE}/launch", glob("launch/*.launch.py")),
        (f"share/{PACKAGE}/rviz", glob("rviz/*.rviz")),
    ],
    install_requires=["setuptools"],
    zip_safe=True,
    entry_points={
        "console_scripts": [
            f"sim_node = {PACKAGE}.sim_node:main",
            f"perception_node = {PACKAGE}.perception_node:main",
            f"planner_node = {PACKAGE}.planner_node:main",
        ],
    },
)
