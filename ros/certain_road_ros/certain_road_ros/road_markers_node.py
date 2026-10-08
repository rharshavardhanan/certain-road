"""The Gazebo road's ground truth and the car's true track, for RViz's top-down view.

Reads an exported world folder (sim/gazebo/export.py: world.json, ground_truth.json) and
publishes, latched, the carriageway, its lane markings and every damage instance as a flat
ellipse in its class colour, with each pothole's id, in Gazebo's `odom` frame (the
OdometryPublisher's, which is the world's). It also publishes the car's track from /odom.
What it draws is the generator's ground truth, never a detection: the detections are on the
camera panel beside it. Every tunable is configs/ros/demo.yaml's `gazebo_view`.
"""

from __future__ import annotations

import json
from pathlib import Path

import rclpy
from geometry_msgs.msg import Point, PoseStamped
from nav_msgs.msg import Odometry
from nav_msgs.msg import Path as PathMsg
from rclpy.executors import ExternalShutdownException
from rclpy.node import Node
from rclpy.qos import QoSProfile, ReliabilityPolicy
from std_msgs.msg import ColorRGBA, Header
from visualization_msgs.msg import Marker, MarkerArray

from certain_road_ros.common import LATCHED, demo_config, yaw_quaternion

_QUEUE = 10


def _rgba(values) -> ColorRGBA:
    r, g, b, a = values
    return ColorRGBA(r=float(r), g=float(g), b=float(b), a=float(a))


class RoadMarkersNode(Node):
    def __init__(self) -> None:
        super().__init__("road_markers_node")
        cfg = demo_config()
        self.cfg, t = cfg["gazebo_view"], cfg["topics"]
        folder = Path(self.declare_parameter("world", "").value)
        meta = json.loads((folder / "world.json").read_text())
        truth = json.loads((folder / meta["ground_truth"]).read_text())
        self.header = Header(frame_id=self.cfg["frame"])
        self.pub = self.create_publisher(MarkerArray, t["gazebo_road"], LATCHED)
        self.pub.publish(self._road(meta["road"], truth))
        self.track = PathMsg(header=self.header)
        self.last_t: float | None = None
        self.pub_path = self.create_publisher(PathMsg, t["gazebo_path"], LATCHED)
        reliable = QoSProfile(depth=_QUEUE, reliability=ReliabilityPolicy.RELIABLE)
        self.create_subscription(Odometry, t["odom"], self._on_odom, reliable)
        self.get_logger().info(
            f"ground truth of {folder.name}: {len(truth['instances'])} instances on "
            f"{t['gazebo_road']}; the car's track on {t['gazebo_path']}"
        )

    def _marker(self, ns: str, i: int, kind: int) -> Marker:
        return Marker(header=self.header, ns=ns, id=i, type=kind, action=Marker.ADD)

    def _road(self, road: dict, truth: dict) -> MarkerArray:
        c = self.cfg
        length, half = road["length_m"], road["lane_width_m"]
        out = []
        surface = self._marker("road", 0, Marker.CUBE)
        surface.pose.position = Point(x=length / 2, y=0.0, z=c["surface_z_m"])
        surface.scale.x, surface.scale.y, surface.scale.z = length, 2 * half, c["flat_m"]
        surface.color = _rgba(c["road_rgba"])
        out.append(surface)
        lines = self._marker("lines", 0, Marker.LINE_LIST)
        lines.scale.x = c["line_width_m"]
        lines.color = _rgba(c["line_rgba"])
        dash, gap = c["centre_dash_m"]
        x = 0.0
        while x < length:  # the centre line's dashes, then both edge lines
            lines.points += [Point(x=x, y=0.0), Point(x=min(x + dash, length), y=0.0)]
            x += dash + gap
        for y in (-half, half):
            lines.points += [Point(x=0.0, y=y), Point(x=length, y=y)]
        out.append(lines)
        for inst in truth["instances"]:
            m = self._marker(inst["cls"], inst["id"], Marker.CYLINDER)
            m.pose.position = Point(x=inst["x_m"], y=inst["y_m"], z=c["flat_m"])
            m.pose.orientation = yaw_quaternion(inst["angle_rad"])
            m.scale.x, m.scale.y, m.scale.z = inst["length_m"], inst["width_m"], c["flat_m"]
            m.color = _rgba(c["class_rgba"][inst["cls"]])
            out.append(m)
            if inst["cls"] == "pothole":
                label = self._marker("pothole_id", inst["id"], Marker.TEXT_VIEW_FACING)
                label.pose.position = Point(x=inst["x_m"], y=inst["y_m"], z=c["label_height_m"])
                label.scale.z = c["label_height_m"]
                label.color = _rgba(c["line_rgba"])
                label.text = f"#{inst['id']}"
                out.append(label)
        return MarkerArray(markers=out)

    def _on_odom(self, msg: Odometry) -> None:
        t = msg.header.stamp.sec + msg.header.stamp.nanosec * 1e-9
        if self.last_t is not None and t - self.last_t < self.cfg["path_every_s"]:
            return
        self.last_t = t
        pose = PoseStamped(header=msg.header)
        pose.header.frame_id = self.cfg["frame"]
        pose.pose = msg.pose.pose
        self.track.poses.append(pose)
        self.track.header.stamp = msg.header.stamp
        self.pub_path.publish(self.track)


def main() -> None:
    rclpy.init()
    node = RoadMarkersNode()
    try:
        rclpy.spin(node)
    except (KeyboardInterrupt, ExternalShutdownException):
        pass
    finally:
        node.destroy_node()
        rclpy.try_shutdown()
