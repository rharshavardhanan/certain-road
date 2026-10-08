"""The survey report from any ROS camera with odometry: frames, detections and /odom in.

    source ros/env.sh
    ROS_DOMAIN_ID=43 ros2 launch certain_road_survey survey.launch.py label:="Gazebo poor road"

Subscribes to the camera (/camera/image_raw, /camera/camera_info), the perception node's
detections (/perception/detections: Model P potholes and Model B cracks, D082) and odometry
(/odom). Each frame is paired with its detections by stamp and handed to `core.RosSurvey`,
which samples the road every `edge.sample_every_m`, counts D006's ROI, scores segments with
`certain_road.survey`, and pictures every counted box. Each time a segment closes, and once
more on shutdown, the node writes runs/ros_survey/<stamp>/: survey.json, gallery.json,
gallery/*.jpg, report.html and report.json, the same report the MuJoCo survey writes.

Nothing here detects, tracks or steers. It is a listener: start it beside any camera source
and perception (the Gazebo world, a robot), drive, then stop it.
"""

from __future__ import annotations

import math
from collections import OrderedDict
from datetime import UTC, datetime
from pathlib import Path

import cv2
import numpy as np
import rclpy
import yaml
from nav_msgs.msg import Odometry as OdometryMsg
from rclpy.executors import ExternalShutdownException
from rclpy.node import Node
from rclpy.qos import qos_profile_sensor_data
from sensor_msgs.msg import CameraInfo, Image
from vision_msgs.msg import Detection2DArray

from certain_road.core.paths import repo_root
from certain_road.survey.rsl import load_config as load_rsl
from certain_road_survey.core import Pose, RosSurvey

CONFIG = "configs/report/ros_survey.yaml"
REPORT_CONFIG = "configs/report/survey_environments.yaml"
BGR_CHANNELS = 3


def stamp_s(stamp) -> float:
    return stamp.sec + stamp.nanosec * 1e-9


def yaw_of(q) -> float:
    return math.atan2(2.0 * (q.w * q.z + q.x * q.y), 1.0 - 2.0 * (q.y * q.y + q.z * q.z))


def to_bgr(msg: Image) -> np.ndarray | None:
    """bgr8 or rgb8 frames; anything else is not pictured (the survey still counts its boxes)."""
    if msg.encoding not in ("bgr8", "rgb8"):
        return None
    rows = np.frombuffer(msg.data, np.uint8).reshape(msg.height, msg.step)
    img = rows[:, : msg.width * BGR_CHANNELS].reshape(msg.height, msg.width, BGR_CHANNELS)
    return cv2.cvtColor(img, cv2.COLOR_RGB2BGR) if msg.encoding == "rgb8" else img.copy()


def to_dets(msg: Detection2DArray) -> list[tuple]:
    out = []
    for d in msg.detections:
        if not d.results:
            continue
        best = max(d.results, key=lambda r: r.hypothesis.score)
        cx, cy = d.bbox.center.position.x, d.bbox.center.position.y
        w, h = d.bbox.size_x, d.bbox.size_y
        out.append(
            (
                best.hypothesis.class_id,
                float(best.hypothesis.score),
                cx - w / 2,
                cy - h / 2,
                cx + w / 2,
                cy + h / 2,
            )
        )
    return out


class SurveyNode(Node):
    def __init__(self) -> None:
        super().__init__("survey_node")
        root = repo_root()
        cfg = yaml.safe_load((root / CONFIG).read_text())
        project = yaml.safe_load((root / "configs/project.yaml").read_text())
        report_cfg = yaml.safe_load((root / REPORT_CONFIG).read_text())
        rsl_cfg = load_rsl(root / report_cfg["rsl_config"])
        label = self.declare_parameter("label", cfg["label"]).value
        stamp = self.declare_parameter("run_stamp", "").value or datetime.now(UTC).strftime(
            "%Y%m%dT%H%M%SZ"
        )
        cfg["chainage"] = self.declare_parameter("chainage", cfg["chainage"]).value
        out = root / cfg["out_dir"] / stamp
        self.survey = RosSurvey(
            cfg,
            project,
            rsl_cfg,
            report_cfg,
            out,
            label=label,
            simulated=bool(self.declare_parameter("simulated", cfg["simulated"]).value),
            run_dir_label=str(out.relative_to(root)),
        )
        self.frames: OrderedDict = OrderedDict()
        self.depth = int(cfg["frames_buffered"])
        t = cfg["topics"]
        self.create_subscription(Image, t["image"], self._on_image, qos_profile_sensor_data)
        self.create_subscription(
            CameraInfo, t["camera_info"], self._on_info, qos_profile_sensor_data
        )
        self.create_subscription(Detection2DArray, t["detections"], self._on_dets, 10)
        self.create_subscription(OdometryMsg, t["odom"], self._on_odom, qos_profile_sensor_data)
        self.get_logger().info(f"surveying {label!r} into {out}")

    def _on_info(self, msg: CameraInfo) -> None:
        if self.survey.camera is None and msg.k[0] > 0:
            self.survey.set_intrinsics(msg.k[0], msg.k[2], msg.k[5])
            self.get_logger().info(
                f"intrinsics f={msg.k[0]:.1f} cx={msg.k[2]:.1f} cy={msg.k[5]:.1f}"
            )

    def _on_odom(self, msg: OdometryMsg) -> None:
        p = msg.pose.pose
        self.survey.pose(
            Pose(stamp_s(msg.header.stamp), p.position.x, p.position.y, yaw_of(p.orientation))
        )

    def _on_image(self, msg: Image) -> None:
        self.frames[(msg.header.stamp.sec, msg.header.stamp.nanosec)] = msg
        while len(self.frames) > self.depth:
            self.frames.popitem(last=False)

    def _on_dets(self, msg: Detection2DArray) -> None:
        key = (msg.header.stamp.sec, msg.header.stamp.nanosec)
        image = self.frames.pop(key, None)
        bgr = to_bgr(image) if image is not None else None
        closed = self.survey.frame(stamp_s(msg.header.stamp), bgr, to_dets(msg))
        if closed is not None:
            self.get_logger().info(
                f"segment {closed['index']} {closed['x0_m']:.0f}-{closed['x1_m']:.0f} m: "
                f"vision-estimated PCI {closed['vision_estimated_pci']:.1f} ({closed['band']})"
            )
            self._write()

    def _write(self) -> Path | None:
        stamp = {"utc": datetime.now(UTC).strftime("%Y-%m-%d %H:%M UTC"), "commit": "ros run"}
        path = self.survey.write(stamp)
        if path is not None and rclpy.ok():
            self.get_logger().info(f"report -> {path}")
        return path

    def finish(self) -> None:
        """Score the trailing partial segment and write. Runs after shutdown, so it prints."""
        self.survey.finish()
        path = self._write()
        print(f"survey_node: final report -> {path}", flush=True)


def main() -> None:
    rclpy.init()
    node = SurveyNode()
    try:
        rclpy.spin(node)
    except (KeyboardInterrupt, ExternalShutdownException):
        pass
    finally:
        node.finish()
        node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()


if __name__ == "__main__":
    main()
