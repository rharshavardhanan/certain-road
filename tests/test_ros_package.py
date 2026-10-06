"""The ROS demo's message conversions and transport (D093). Skipped where ROS is absent.

CI has no ROS, so these run only on a machine with `source ros/env.sh` done (the Jetson).
The pure halves, the renderer and the Twist-unit kinematics, are tested without ROS in
test_sim_camera_image.py and test_sim_model.py.
"""

import sys

import numpy as np
import pytest

pytest.importorskip("rclpy")
pytest.importorskip("vision_msgs")

from certain_road.core.paths import repo_root  # noqa: E402

sys.path.insert(0, str(repo_root() / "ros" / "certain_road_ros"))

from certain_road_ros.common import (  # noqa: E402
    detections_from,
    detections_msg,
    image_msg,
    image_rgb,
)
from certain_road_ros.transport import RosTransport, twist_command  # noqa: E402
from geometry_msgs.msg import Twist  # noqa: E402
from std_msgs.msg import Header  # noqa: E402

from certain_road.artifacts.schema import Detection  # noqa: E402
from certain_road.canbus.protocol import Action, Command, Mode  # noqa: E402
from certain_road.sim.model import load_robot  # noqa: E402

ROBOT = load_robot(repo_root() / "configs" / "sim" / "robot.yaml")


class _Recorder:
    def __init__(self) -> None:
        self.sent: list[Twist] = []

    def publish(self, msg: Twist) -> None:
        self.sent.append(msg)


@pytest.mark.parametrize("encoding", ["rgb8", "bgr8"])
def test_image_round_trip(encoding):
    rng = np.random.default_rng(0)
    pixels = rng.integers(0, 256, size=(48, 64, 3), dtype=np.uint8)
    msg = image_msg(pixels, Header(frame_id="camera_link"), encoding)
    back = image_rgb(msg)
    expected = pixels[..., ::-1] if encoding == "bgr8" else pixels
    assert np.array_equal(back, expected)


def test_detections_round_trip_exactly():
    dets = [
        Detection("pothole", 0.9, 100.0, 200.5, 180.25, 260.0, 640, 640),
        Detection("linear_crack", 0.4, 0.0, 0.0, 640.0, 12.0, 640, 640),
    ]
    back = detections_from(detections_msg(dets, Header()), 640, 640)
    assert back == dets


def test_transport_delivers_the_command_the_planner_sent():
    pub = _Recorder()
    transport = RosTransport(pub, ROBOT)
    sent = Command(Action.FORWARD, 0.35, -0.7, Mode.AUTONOMOUS)
    transport.send(sent)
    got = twist_command(pub.sent[-1], ROBOT)
    assert got.action is sent.action
    assert got.speed == pytest.approx(sent.speed, abs=1e-12)
    assert got.steer == pytest.approx(sent.steer, abs=1e-12)


def test_stop_arrives_as_stop():
    pub = _Recorder()
    RosTransport(pub, ROBOT).send(Command(Action.STOP, 0.0, 0.0, Mode.AUTONOMOUS))
    assert (pub.sent[-1].linear.x, pub.sent[-1].angular.z) == (0.0, 0.0)
    assert twist_command(pub.sent[-1], ROBOT).action is Action.STOP
