"""The ROS demo's message conversions, pairing and transport (D093). Skipped where ROS is absent.

CI has no ROS, so these run only on a machine with `source ros/env.sh` done (the Jetson).
The pure halves are tested without ROS: the renderer and the Twist-unit kinematics in
test_sim_camera_image.py and test_sim_model.py, the video's ground truth in
test_ros_video.py, the CAN byte path in test_ros_can.py.
"""

import sys

import numpy as np
import pytest

pytest.importorskip("rclpy")
pytest.importorskip("vision_msgs")

from certain_road.core.paths import repo_root  # noqa: E402

sys.path.insert(0, str(repo_root() / "ros" / "certain_road_ros"))

from certain_road_ros.common import (  # noqa: E402
    StampPairer,
    camera_info_msg,
    detections_from,
    detections_msg,
    frame_info_from,
    frame_info_msg,
    image_msg,
    image_rgb,
)
from certain_road_ros.transport import RosTransport, twist_command  # noqa: E402
from certain_road_ros.video import FrameInfo  # noqa: E402
from diagnostic_msgs.msg import DiagnosticStatus  # noqa: E402
from geometry_msgs.msg import Twist  # noqa: E402
from std_msgs.msg import Header  # noqa: E402

from certain_road.artifacts.schema import Detection  # noqa: E402
from certain_road.canbus.protocol import Action, Command, Mode  # noqa: E402
from certain_road.sim.model import RobotState, load_robot  # noqa: E402
from certain_road.sim.project import project_pothole  # noqa: E402

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


def test_detections_take_the_frame_size_they_are_given():
    """The planner judges boxes against the camera's own size (video 1280x720, sim 640x640)."""
    det = Detection("pothole", 0.8, 600.0, 500.0, 700.0, 700.0, 1280, 720)
    (back,) = detections_from(detections_msg([det], Header()), 1280, 720)
    assert back == det
    assert back.y2 / back.img_h == pytest.approx(700 / 720)


def test_sim_camera_info_matches_the_projection():
    """K from hfov puts a point where certain_road.sim.project puts it: the principal point
    at the centre and f = (w/2) / tan(hfov/2), square pixels."""
    cam = ROBOT.camera
    info = camera_info_msg(cam.img_w, cam.img_h, Header(frame_id="camera_link"), cam.hfov_rad)
    assert (info.width, info.height) == (cam.img_w, cam.img_h)
    f, cx = info.k[0], info.k[2]
    assert info.k[4] == f and info.k[5] == cam.img_h / 2
    # a pothole straight ahead, 0.4 m to the left: its box centre's u from the pinhole model
    state = RobotState(x=0.0, y=0.0, heading=0.0, speed=0.0)
    box = project_pothole(1.0, 0.4, 0.05, state, cam)
    u = cx - f * 0.4 / 1.0
    assert (box.x1 + box.x2) / 2 == pytest.approx(u, abs=1.0)


def test_video_camera_info_has_no_intrinsics():
    info = camera_info_msg(1280, 720, Header())
    assert (info.width, info.height) == (1280, 720)
    assert all(v == 0.0 for v in info.k)  # ROS reads K[0] == 0 as uncalibrated


def test_frame_info_round_trips_and_flags_a_pothole_in_view():
    info = FrameInfo(
        "2DV-cYmIvT4", 4800, 160.0, (7, 8, 9), 17, "LOCKSTEP", True, "OPEN LOOP", "CC BY"
    )
    msg = frame_info_msg(info, Header(frame_id="camera_link"))
    assert frame_info_from(msg) == info
    assert msg.status[0].level == DiagnosticStatus.WARN
    assert msg.status[0].message == "GROUND TRUTH: potholes #7, #8, #9 of 17 in view"
    clear = FrameInfo("2DV-cYmIvT4", 3600, 120.0, (), 17, "LOCKSTEP", True, "OPEN LOOP", "CC BY")
    assert frame_info_msg(clear, Header()).status[0].level == DiagnosticStatus.OK


def test_a_frame_needing_nothing_is_released_at_once():
    p = StampPairer(["ground_truth", "frame_info"], depth=4)
    assert p.add_primary((1, 0), "img1", set()) == [("img1", {})]


def test_a_frame_waits_for_its_ground_truth_whichever_arrives_first():
    p = StampPairer(["ground_truth", "frame_info"], depth=4)
    assert p.add_primary((1, 0), "img1", {"ground_truth"}) == []
    assert p.add_companion("ground_truth", (2, 0), "gt2") == []  # another frame's
    assert p.add_companion("ground_truth", (1, 0), "gt1") == [("img1", {"ground_truth": "gt1"})]
    # companion first, frame second
    assert p.add_primary((2, 0), "img2", {"ground_truth"}) == [("img2", {"ground_truth": "gt2"})]


def test_companions_already_in_come_along_unasked():
    p = StampPairer(["ground_truth", "frame_info"], depth=4)
    p.add_companion("frame_info", (3, 0), "info3")
    assert p.add_primary((3, 0), "img3", set()) == [("img3", {"frame_info": "info3"})]


def test_waiting_frames_are_bounded_oldest_first():
    p = StampPairer(["ground_truth"], depth=2)
    for k in range(3):
        p.add_primary((k, 0), f"img{k}", {"ground_truth"})
    assert p.add_companion("ground_truth", (0, 0), "gt0") == []  # img0 was dropped
    assert p.add_companion("ground_truth", (2, 0), "gt2") == [("img2", {"ground_truth": "gt2"})]
