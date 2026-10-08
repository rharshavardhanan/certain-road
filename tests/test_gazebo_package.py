"""The ROS package's generated files, the car's physics numbers, and the launch helpers.

ros/certain_road_gz runs where this repository's configs are absent (another PC with only
ROS 2 and Gazebo), so its car model, bridge table and frame file are generated from
configs/sim/gazebo.yaml and committed. These check they still match, that the car carries
the design camera, and that the launch helpers find, edit and place things correctly.
None needs ROS or Gazebo: launch_args.py is plain Python.
"""

import math
import sys
import xml.etree.ElementTree as ET

import numpy as np
import pytest
import yaml

from certain_road.core.paths import repo_root
from sim.gazebo import package
from sim.gazebo.evaluate import rpy_mat
from sim.gazebo.vehicle import CORNERS, suspension
from sim.mujoco.scene import design_camera

sys.path.insert(0, str(repo_root() / "ros" / "certain_road_gz"))
from certain_road_gz import launch_args  # noqa: E402

PKG = repo_root() / "ros/certain_road_gz"
GZ = package.load()
SDF = (PKG / "models/certain_road_car/model.sdf").read_text()
CAR = yaml.safe_load((PKG / "config/car.yaml").read_text())
CAM = design_camera()


def test_committed_package_files_match_the_config():
    assert package.stale() == [], "run: python -m sim.gazebo.package"


def test_package_files_hold_no_machine_paths():
    for path in package.generated():
        text = (repo_root() / path).read_text()
        assert "/home/" not in text and "/Users/" not in text and "file://" not in text


def test_the_car_carries_the_design_camera():
    sensor = ET.fromstring(SDF).find(".//sensor[@type='camera']")
    cam = sensor.find("camera")
    assert float(cam.find("horizontal_fov").text) == pytest.approx(CAM["hfov"])
    assert int(cam.find("image/width").text) == CAM["w"]
    assert int(cam.find("image/height").text) == CAM["h"]
    x, y, z, roll, pitch, yaw = (float(v) for v in sensor.find("pose").text.split())
    assert z + GZ["vehicle"]["cg_height_m"] == pytest.approx(CAM["height"])
    assert pitch == pytest.approx(CAM["pitch"], abs=1e-6) and roll == yaw == 0.0
    assert CAR["camera_xyz"] == pytest.approx([x, y, z]) and CAR["camera_rpy"][1] == pytest.approx(
        pitch
    )
    # in front of the body: nothing of the car is in view
    assert x >= GZ["vehicle"]["chassis"]["length_m"] / 2


def test_suspension_holds_the_static_load_at_zero_travel():
    veh, g = GZ["vehicle"], GZ["physics"]["gravity_mps2"]
    s = suspension(veh, g)
    corner = veh["chassis"]["mass_kg"] / len(CORNERS)
    # spring force -k (q - q_ref) at q = 0 balances the corner's weight
    assert s["stiffness"] * (0 - s["reference"]) == pytest.approx(corner * g)
    assert math.sqrt(s["stiffness"] / corner) / (2 * math.pi) == pytest.approx(
        veh["suspension"]["ride_hz"]
    )
    assert s["damping"] / (2 * math.sqrt(s["stiffness"] * corner)) == pytest.approx(
        veh["suspension"]["damping_ratio"]
    )
    legs = [j for j in ET.fromstring(SDF).iter("joint") if j.get("name").endswith("_suspension")]
    assert len(legs) == 4 and all(j.get("type") == "prismatic" for j in legs)


def test_the_bridge_carries_every_topic_the_rest_of_the_stack_uses():
    rows = yaml.safe_load((PKG / "config/bridge.yaml").read_text())
    ros = {r["ros_topic_name"]: r for r in rows}
    assert {
        "/camera/image_raw",
        "/camera/camera_info",
        "/cmd_vel",
        "/odom",
        "/tf",
        "/clock",
    } <= set(ros)
    assert ros["/cmd_vel"]["direction"] == "ROS_TO_GZ"
    assert ros["/cmd_vel"]["ros_type_name"] == "geometry_msgs/msg/Twist"
    assert ros["/clock"]["direction"] == "GZ_TO_ROS"
    plugins = {p.get("name"): p for p in ET.fromstring(SDF).iter("plugin")}
    ack = plugins["gz::sim::systems::AckermannSteering"]
    assert ack.find("topic").text == ros["/cmd_vel"]["gz_topic_name"]
    odom = plugins["gz::sim::systems::OdometryPublisher"]
    assert odom.find("odom_topic").text == ros["/odom"]["gz_topic_name"]
    assert odom.find("dimensions").text == "3"  # the true pose carries pitch and roll


def test_with_camera_overrides_only_what_is_given():
    low = CAR["camera_low"]
    out = launch_args.with_camera(SDF, str(low["w"]), str(low["h"]), str(low["rate_hz"]))
    assert launch_args.camera_settings(out) == {
        "w": low["w"],
        "h": low["h"],
        "rate_hz": low["rate_hz"],
    }
    same = launch_args.camera_settings(launch_args.with_camera(SDF))
    assert same == {"w": CAM["w"], "h": CAM["h"], "rate_hz": GZ["camera"]["rate_hz"]}
    assert (
        ET.fromstring(out).find(".//horizontal_fov").text
        == ET.fromstring(SDF).find(".//horizontal_fov").text
    )


def test_world_dir_resolves_folder_file_preset_and_env(tmp_path, monkeypatch):
    w = tmp_path / "worlds" / "poor_seed3"
    w.mkdir(parents=True)
    (w / "world.sdf").write_text("<sdf/>")
    assert launch_args.world_dir(str(w), "", "x", "0", tmp_path) == w
    assert launch_args.world_dir(str(w / "world.sdf"), "", "x", "0", tmp_path) == w
    assert launch_args.world_dir("", "worlds", "poor", "3", tmp_path) == w  # relative to cwd
    monkeypatch.setenv(launch_args.WORLDS_ENV, str(tmp_path / "worlds"))
    assert launch_args.world_dir("", "", "poor", "3", tmp_path / "elsewhere") == w
    with pytest.raises(FileNotFoundError, match="sim.gazebo.export"):
        launch_args.world_dir("", "", "good", "9", tmp_path)


def test_spawn_and_static_transforms():
    meta = {"world_name": "certain_road", "spawn": {"x": 5.0, "y": 1.75, "yaw": 0.0}}
    a = launch_args.spawn_args(meta, CAR, repo_root() / "car.sdf")
    assert a[a.index("-y") + 1] == "1.75" and a[a.index("-z") + 1] == str(CAR["spawn_z_m"])
    body, optical = launch_args.static_tf_args(CAR)
    assert body[body.index("--child-frame-id") + 1] == CAR["frames"]["camera"]
    rpy = [float(optical[optical.index(f"--{k}") + 1]) for k in ("roll", "pitch", "yaw")]
    r = rpy_mat(*rpy)  # columns: the optical frame's axes in the camera body frame
    np.testing.assert_allclose(r[:, 2], [1, 0, 0], atol=1e-12)  # z looks forward
    np.testing.assert_allclose(r[:, 0], [0, -1, 0], atol=1e-12)  # x is image right
    np.testing.assert_allclose(r[:, 1], [0, 0, -1], atol=1e-12)  # y is image down
