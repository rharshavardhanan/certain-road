"""The Gazebo closed loop's STAND-IN DRIVER: holds the lane while the planner is not steering.

NOT UNDER TEST. The planner (the code under test) has no lane keeping: NORMAL means steer 0,
and over 500 m the pothole knocks alone take a car out of its lane. A driver would hold it,
so this node does, from Gazebo's TRUE pose, which no real car has. Its rule is
`certain_road_ros.lane_keep`: in NORMAL and WARNING it sends the planner's speed with its own
yaw rate back to the lane centre; in AVOID_LEFT, AVOID_RIGHT and STOP it passes the
planner's Twist unchanged. The CAN frames carry the planner's own Command, never this.

In: the planner's Twist (`topics.planner_cmd_vel`; gazebo.launch.py remaps the planner's
/cmd_vel there), its drive state, and /odom. Out: the car's /cmd_vel at `lane_keeper.rate_hz`
of simulated time, and /lane_keeper/state. If the planner falls silent for
`planner_timeout_s` the car is stopped, as a vehicle's own watchdog would.

`alone:=true` is the baseline run: no planner at all. The stand-in drives the policy's NORMAL
command through the vehicle profile (20 km/h for the car) and holds the lane, which is what
the car does with no reaction to potholes. At shutdown it writes `lane_keeper.json` beside
the planner's logs: how often it steered, and the largest lateral error.
"""

from __future__ import annotations

import json

import rclpy
from geometry_msgs.msg import Twist
from nav_msgs.msg import Odometry
from rclpy.executors import ExternalShutdownException
from rclpy.node import Node
from rclpy.qos import QoSProfile, ReliabilityPolicy
from std_msgs.msg import String

from certain_road.driving.controller import command_for
from certain_road.driving.decision import DriveState, load_policy
from certain_road.sim.model import command_velocity, load_robot
from certain_road_ros.common import LATEST, demo_config, profile, repo_path, run_dir
from certain_road_ros.lane_keep import blend, heading, yaw_rate

_QUEUE = 10


class LaneKeeperNode(Node):
    def __init__(self) -> None:
        super().__init__("lane_keeper_node")
        cfg = demo_config()
        self.cfg, t = cfg["lane_keeper"], cfg["topics"]
        self.lane_y = float(self.declare_parameter("lane_y", 0.0).value)
        self.alone = bool(self.declare_parameter("alone", False).value)
        vehicle, vehicle_path, _, _ = profile(self.declare_parameter("vehicle", "").value)
        robot = load_robot(vehicle_path)
        policy = load_policy(repo_path("configs", "driving", "decision.yaml"))
        self.cruise = command_velocity(command_for(DriveState.NORMAL, policy), robot)[0]
        self.out = run_dir(self.declare_parameter("run_stamp", "").value)

        self.planner: tuple[float, float] | None = None
        self.planner_at = None
        self.state = str(DriveState.NORMAL)
        self.pose: tuple[float, float] | None = None  # lateral offset, heading
        self.label = ""
        self.ticks = {"steered": 0, "passed": 0, "stopped_silent": 0, "alone": 0}
        self.max_lateral = 0.0

        reliable = QoSProfile(depth=_QUEUE, reliability=ReliabilityPolicy.RELIABLE)
        self.pub = self.create_publisher(Twist, t["cmd_vel"], _QUEUE)
        self.pub_state = self.create_publisher(String, t["lane_keeper_state"], LATEST)
        self.create_subscription(Twist, t["planner_cmd_vel"], self._on_planner, reliable)
        self.create_subscription(String, t["drive_state"], self._on_state, LATEST)
        self.create_subscription(Odometry, t["odom"], self._on_odom, reliable)
        self.create_timer(1.0 / self.cfg["rate_hz"], self._tick)
        who = "ALONE (baseline: no planner)" if self.alone else "following the planner"
        self.get_logger().info(
            f"STAND-IN DRIVER, not under test: {who}; vehicle {vehicle}, lane y "
            f"{self.lane_y} m, steers in {self.cfg['steers_in']}, cruise {self.cruise:.3f} m/s; "
            f"logs: {self.out}"
        )

    def _on_planner(self, msg: Twist) -> None:
        self.planner = (msg.linear.x, msg.angular.z)
        self.planner_at = self.get_clock().now()

    def _on_state(self, msg: String) -> None:
        self.state = msg.data

    def _on_odom(self, msg: Odometry) -> None:
        p, q = msg.pose.pose.position, msg.pose.pose.orientation
        self.pose = (p.y - self.lane_y, heading(q.w, q.x, q.y, q.z))
        self.max_lateral = max(self.max_lateral, abs(self.pose[0]))

    def _tick(self) -> None:
        if self.pose is None:
            return
        keep = yaw_rate(*self.pose, self.cfg)
        if self.alone:
            (linear, yaw), label = (self.cruise, keep), "alone: cruise, holding the lane"
            self.ticks["alone"] += 1
        elif self.planner is None:
            return  # nothing from the planner yet: the car stands
        elif (self.get_clock().now() - self.planner_at).nanoseconds / 1e9 > self.cfg[
            "planner_timeout_s"
        ]:
            (linear, yaw), label = (0.0, 0.0), "planner silent: stopped"
            self.ticks["stopped_silent"] += 1
        else:
            (linear, yaw), steering = blend(self.state, self.planner, keep, self.cfg)
            label = f"{self.state}: " + ("holding the lane" if steering else "planner steers")
            self.ticks["steered" if steering else "passed"] += 1
        msg = Twist()
        msg.linear.x, msg.angular.z = float(linear), float(yaw)
        self.pub.publish(msg)
        if label != self.label:
            self.label = label
            self.pub_state.publish(String(data=f"STAND-IN DRIVER (not under test): {label}"))

    def write_summary(self) -> None:
        total = sum(self.ticks.values())
        row = {
            "stand_in_driver": "not under test: holds the lane from the true pose",
            "alone": self.alone,
            "lane_y": self.lane_y,
            "ticks": self.ticks,
            "steered_share": round(self.ticks["steered"] / total, 4) if total else None,
            "max_abs_lateral_m": round(self.max_lateral, 4),
        }
        (self.out / "lane_keeper.json").write_text(json.dumps(row, indent=1))


def main() -> None:
    rclpy.init()
    node = LaneKeeperNode()
    try:
        rclpy.spin(node)
    except (KeyboardInterrupt, ExternalShutdownException):
        pass
    finally:
        node.write_summary()
        node.destroy_node()
        rclpy.try_shutdown()
