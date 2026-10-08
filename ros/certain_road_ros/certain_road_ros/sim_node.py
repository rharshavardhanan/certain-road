"""The simulated vehicle as a ROS node: the 2D simulator's world, camera and actuator.

Every `dt` of the scenario it steps the bicycle model with the latest /cmd_vel
(`certain_road.sim.model.step`), then publishes what the robot now sees and where it
is: the rendered camera frame (`certain_road.sim.camera_image`), the ground-truth boxes
`certain_road.sim.project` gives for that same frame, the pose, TF and the path. The
camera's size and pinhole intrinsics go out once, latched, on /camera/camera_info, which
is where the planner reads the image size from.

Scenarios are `certain_road.sim.scenario.SCENARIOS`, run in turn, each for its own frame
count as `run_scenario` runs it. A latched /sim/scenario message marks each start, so
the planner resets when the vehicle does.

The order inside an episode mirrors `run_scenario`: frame k is published from state k,
and the command decided on it moves the robot to state k+1 on the next tick. This node
decides nothing.
"""

from __future__ import annotations

import rclpy
from geometry_msgs.msg import Point, PoseStamped, TransformStamped, Twist, Vector3
from nav_msgs.msg import Path
from rclpy.executors import ExternalShutdownException
from rclpy.node import Node
from sensor_msgs.msg import CameraInfo, Image
from std_msgs.msg import ColorRGBA, Header, String
from tf2_ros import StaticTransformBroadcaster, TransformBroadcaster
from vision_msgs.msg import Detection2DArray
from visualization_msgs.msg import Marker, MarkerArray

from certain_road.canbus.protocol import Action, Command, Mode
from certain_road.sim.camera_image import load_palette, render_frame
from certain_road.sim.model import load_robot, step
from certain_road.sim.project import project_pothole
from certain_road.sim.scenario import SCENARIOS
from certain_road_ros.common import (
    LATCHED,
    camera_info_msg,
    demo_config,
    detections_msg,
    image_msg,
    pitch_quaternion,
    repo_path,
    yaw_quaternion,
)
from certain_road_ros.transport import twist_command

STOP = Command(Action.STOP, 0.0, 0.0, Mode.AUTONOMOUS)
_IMAGE_QUEUE = 2
_CMD_QUEUE = 10


def _rgba(values: list[float]) -> ColorRGBA:
    r, g, b, a = values
    return ColorRGBA(r=r, g=g, b=b, a=a)


class SimNode(Node):
    def __init__(self) -> None:
        super().__init__("sim_node")
        cfg = demo_config()
        self.cfg, self.topics, self.frames = cfg["sim"], cfg["topics"], cfg["frames"]
        self.robot = load_robot(repo_path("configs", "sim", "robot.yaml"))
        self.palette = load_palette(repo_path("configs", "sim", "camera_image.yaml"))

        requested = self.declare_parameter("scenarios", "").value
        names = [n.strip() for n in requested.split(",") if n.strip()] or self.cfg["scenarios"]
        unknown = sorted(set(names) - set(SCENARIOS))
        if unknown:
            raise ValueError(f"unknown scenarios {unknown}; known: {sorted(SCENARIOS)}")
        self.scenarios = [SCENARIOS[n] for n in names]
        dts = {s.dt for s in self.scenarios}
        if len(dts) != 1:
            raise ValueError(f"the scenarios run on one timer, so must share one dt; got {dts}")
        self.dt = dts.pop()

        t = self.topics
        self.pub_image = self.create_publisher(Image, t["image"], _IMAGE_QUEUE)
        self.pub_truth = self.create_publisher(Detection2DArray, t["ground_truth"], _IMAGE_QUEUE)
        self.pub_pose = self.create_publisher(PoseStamped, t["pose"], _IMAGE_QUEUE)
        self.pub_path = self.create_publisher(Path, t["path"], _IMAGE_QUEUE)
        self.pub_markers = self.create_publisher(MarkerArray, t["world_markers"], _IMAGE_QUEUE)
        self.pub_scenario = self.create_publisher(String, t["scenario"], LATCHED)
        self.pub_info = self.create_publisher(CameraInfo, t["camera_info"], LATCHED)
        cam = self.robot.camera
        info_header = Header(stamp=self.get_clock().now().to_msg(), frame_id=self.frames["camera"])
        self.pub_info.publish(camera_info_msg(cam.img_w, cam.img_h, info_header, cam.hfov_rad))
        self.create_subscription(Twist, t["cmd_vel"], self._on_cmd, _CMD_QUEUE)
        self.tf = TransformBroadcaster(self)
        self.static_tf = StaticTransformBroadcaster(self)
        self.static_tf.sendTransform(self._camera_mount())

        self.episode = -1
        self.started = False
        self.create_timer(self.dt, self._tick)
        self.get_logger().info("waiting for perception and planner before starting the clock")

    # ---- episode bookkeeping ---------------------------------------------------------

    def _next_episode(self) -> None:
        self.episode += 1
        self.scenario = self.scenarios[self.episode % len(self.scenarios)]
        self.state = self.scenario.start
        self.frame = 0
        self.command = STOP
        self.cmd_age = 0
        self.timed_out = False
        self.path = Path(header=Header(frame_id=self.frames["world"]))
        self.pub_scenario.publish(String(data=self.scenario.name))
        self.get_logger().info(
            f"episode {self.episode}: '{self.scenario.name}' "
            f"({len(self.scenario.commands)} frames at {1 / self.dt:.0f} Hz), "
            f"expect {self.scenario.expect}. {self.scenario.description}"
        )

    def _on_cmd(self, msg: Twist) -> None:
        self.command = twist_command(msg, self.robot)
        self.cmd_age = 0
        self.timed_out = False

    def _loop_connected(self) -> bool:
        """Every link of the loop is up: frames and ground truth have a reader, detections
        have a reader, and someone publishes /cmd_vel. Starting before discovery finishes
        would publish the first frames to nobody and cut the first episode short."""
        t = self.topics
        return (
            self.count_subscribers(t["image"]) > 0
            and self.count_subscribers(t["ground_truth"]) > 0
            and self.count_subscribers(t["detections"]) > 0
            and self.count_publishers(t["cmd_vel"]) > 0
        )

    def _tick(self) -> None:
        if not self.started:
            if not self._loop_connected():
                return
            self.started = True
            self._next_episode()
        elif self.frame >= len(self.scenario.commands):
            self._next_episode()
        elif self.frame > 0:
            command = self.command
            if self.cmd_age >= self.cfg["cmd_timeout_frames"]:
                command = STOP
                if not self.timed_out:
                    self.timed_out = True
                    self.get_logger().warning(
                        f"no /cmd_vel for {self.cmd_age} frames: vehicle watchdog stops"
                    )
            self.state = step(self.state, command, self.dt, self.robot)
            self.cmd_age += 1
        self._publish()
        self.frame += 1

    # ---- what the robot sees and where it is -----------------------------------------

    def _publish(self) -> None:
        stamp = self.get_clock().now().to_msg()
        cam = Header(stamp=stamp, frame_id=self.frames["camera"])
        world = Header(stamp=stamp, frame_id=self.frames["world"])
        s, camera = self.state, self.robot.camera

        truth = [
            d
            for p in self.scenario.potholes
            if (d := project_pothole(p.x, p.y, p.radius, s, camera)) is not None
        ]
        self.pub_truth.publish(detections_msg(truth, cam))
        frame = render_frame(s, self.scenario.potholes, camera, self.palette)
        self.pub_image.publish(image_msg(frame, cam, "rgb8"))

        pose = PoseStamped(header=world)
        pose.pose.position = Point(x=s.x, y=s.y, z=0.0)
        pose.pose.orientation = yaw_quaternion(s.heading)
        self.pub_pose.publish(pose)
        self.path.header.stamp = stamp
        self.path.poses.append(pose)
        self.pub_path.publish(self.path)

        tf = TransformStamped(header=world, child_frame_id=self.frames["robot"])
        tf.transform.translation = Vector3(x=s.x, y=s.y, z=0.0)
        tf.transform.rotation = pose.pose.orientation
        self.tf.sendTransform(tf)

        self.pub_markers.publish(self._markers(world))

    def _camera_mount(self) -> TransformStamped:
        tf = TransformStamped(
            header=Header(stamp=self.get_clock().now().to_msg(), frame_id=self.frames["robot"]),
            child_frame_id=self.frames["camera"],
        )
        tf.transform.translation = Vector3(
            x=self.cfg["camera_mount_x_m"], y=0.0, z=self.robot.camera.height_m
        )
        tf.transform.rotation = pitch_quaternion(self.robot.camera.pitch_rad)
        return tf

    def _markers(self, world: Header) -> MarkerArray:
        cfg = self.cfg
        out = MarkerArray()
        out.markers.append(Marker(header=world, action=Marker.DELETEALL))

        (x0, x1), (y0, y1) = cfg["road_marker"]["x"], cfg["road_marker"]["y"]
        road = Marker(header=world, ns="road", id=0, type=Marker.CUBE, action=Marker.ADD)
        flat = cfg["flat_marker_m"]
        road.pose.position = Point(x=(x0 + x1) / 2, y=(y0 + y1) / 2, z=-flat)
        road.scale = Vector3(x=x1 - x0, y=y1 - y0, z=flat)
        road.color = _rgba(cfg["road_marker"]["rgba"])
        out.markers.append(road)

        for i, p in enumerate(self.scenario.potholes):
            m = Marker(header=world, ns="potholes", id=i, type=Marker.CYLINDER, action=Marker.ADD)
            m.pose.position = Point(x=p.x, y=p.y, z=flat)
            m.scale = Vector3(x=2 * p.radius, y=2 * p.radius, z=2 * flat)
            m.color = _rgba(cfg["pothole_rgba"])
            out.markers.append(m)

        body = Header(stamp=world.stamp, frame_id=self.frames["robot"])
        h = cfg["marker_height_m"]
        robot = Marker(header=body, ns="robot", id=0, type=Marker.CUBE, action=Marker.ADD)
        robot.pose.position = Point(x=0.0, y=0.0, z=h / 2)
        robot.scale = Vector3(x=self.robot.length_m, y=self.robot.width_m, z=h)
        robot.color = _rgba(cfg["robot_rgba"])
        out.markers.append(robot)
        return out


def main() -> None:
    rclpy.init()
    node = SimNode()
    try:
        rclpy.spin(node)
    except (KeyboardInterrupt, ExternalShutdownException):
        pass
    finally:
        node.destroy_node()
        rclpy.try_shutdown()
