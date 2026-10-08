"""ament_python package for the ROS 2 survey. Built by `colcon build` from ros/."""

from glob import glob

from setuptools import setup

PACKAGE = "certain_road_survey"

setup(
    name=PACKAGE,
    version="0.1.0",
    packages=[PACKAGE],
    data_files=[
        ("share/ament_index/resource_index/packages", [f"resource/{PACKAGE}"]),
        (f"share/{PACKAGE}", ["package.xml"]),
        (f"share/{PACKAGE}/launch", glob("launch/*.launch.py")),
    ],
    install_requires=["setuptools"],
    zip_safe=True,
    entry_points={"console_scripts": [f"survey_node = {PACKAGE}.survey_node:main"]},
)
