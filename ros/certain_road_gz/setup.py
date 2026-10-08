"""ament_python package for the Gazebo world (sim/gazebo). Built by `colcon build` from ros/."""

from glob import glob

from setuptools import setup

PACKAGE = "certain_road_gz"

setup(
    name=PACKAGE,
    version="0.1.0",
    packages=[PACKAGE],
    data_files=[
        ("share/ament_index/resource_index/packages", [f"resource/{PACKAGE}"]),
        (f"share/{PACKAGE}", ["package.xml"]),
        (f"share/{PACKAGE}/launch", glob("launch/*.launch.py")),
        (f"share/{PACKAGE}/config", glob("config/*.yaml")),
        (f"share/{PACKAGE}/models/certain_road_car", glob("models/certain_road_car/*")),
    ],
    install_requires=["setuptools"],
    zip_safe=True,
)
