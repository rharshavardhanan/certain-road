"""CAN frames off the bus, decoded: what the planner's decisions look like on the wire.

Listens on the bus `configs/ros/demo.yaml` names (socketcan `vcan0` on the Jetson, made by
`ros/install_gazebo_can.sh`) for the drive-command arbitration ID of
`configs/canbus/transport.yaml`, decodes each payload with `Command.from_bytes` and
publishes one readable line per frame on /can/decoded, for example

    101#0159A701 -> FORWARD speed 0.35 steer +0.00 AUTONOMOUS

The left half is the frame as `candump vcan0` prints it, so a terminal running candump
beside the launch shows the same frames raw: decision -> CAN frame -> decoded. Every frame
is also written to `runs/ros/<stamp>/can_frames.jsonl`. This node only listens; it is a
separate socket from the planner's, so what it reads really crossed the bus. A reader thread
blocks on the socket (the kernel filters on the ID), so the node costs nothing between
frames.

The provisional 4-byte layout (`certain_road.canbus.protocol`) is the contract here too: a
frame that does not decode is reported, not dropped. The payload's speed and steer are
normalised; `vehicle:=` names the profile (configs/ros/demo.yaml `profiles`, as the
planner's) that reads them back as m/s and rad/s, the same numbers the frame's /cmd_vel
carried.
"""

from __future__ import annotations

import json
import threading

import can
import rclpy
from rclpy.executors import ExternalShutdownException
from rclpy.node import Node
from std_msgs.msg import String

from certain_road.sim.model import command_velocity, load_robot
from certain_road_ros.can_link import CAN_MODES, can_transport_config, describe_frame
from certain_road_ros.common import LATEST, demo_config, profile, repo_path, run_dir

_STANDARD_ID_MASK = 0x7FF  # all 11 bits of a standard CAN ID must match


class CanMonitorNode(Node):
    def __init__(self) -> None:
        super().__init__("can_monitor_node")
        cfg = demo_config()
        self.cfg = cfg["can"]
        mode = self.declare_parameter("can", "").value or str(self.cfg["enabled"]).lower()
        if mode not in CAN_MODES:
            raise ValueError(f"can must be one of {CAN_MODES}, got {mode!r}")
        self.out_dir = run_dir(self.declare_parameter("run_stamp", "").value)
        self.vehicle, vehicle_path, _, _ = profile(self.declare_parameter("vehicle", "").value)
        self.robot = load_robot(vehicle_path)
        self.bus = None
        self.frames = self.undecoded = 0
        self.last_line = ""
        if mode == "false":
            self.get_logger().info("CAN off (can:=false): nothing to monitor")
            return

        bus_cfg = can_transport_config(repo_path("configs", "canbus", "transport.yaml"), self.cfg)
        self.arbitration_id = bus_cfg.arbitration_id
        where = f"{bus_cfg.interface}/{bus_cfg.channel} id 0x{self.arbitration_id:X}"
        try:
            self.bus = can.Bus(
                channel=bus_cfg.channel,
                interface=bus_cfg.interface,
                can_filters=[
                    {
                        "can_id": self.arbitration_id,
                        "can_mask": _STANDARD_ID_MASK,
                        "extended": False,
                    }
                ],
            )
        except (OSError, can.CanError) as exc:
            if mode == "true":
                raise
            self.get_logger().warning(f"CAN unavailable on {where} ({exc}): nothing to monitor")
            return

        self.pub = self.create_publisher(String, cfg["topics"]["can_decoded"], LATEST)
        self.log = (self.out_dir / "can_frames.jsonl").open("a", buffering=1)
        self.running = True
        self.reader = threading.Thread(target=self._read, name="can_reader", daemon=True)
        self.reader.start()
        self.get_logger().info(
            f"listening on {where}; decoded frames on {cfg['topics']['can_decoded']}. "
            f"Raw: candump {bus_cfg.channel}"
        )

    def _read(self) -> None:
        """Blocks on the bus; wakes every recv_timeout_s to notice shutdown."""
        while self.running:
            msg = self.bus.recv(timeout=self.cfg["recv_timeout_s"])
            if msg is None or not self.running or not rclpy.ok(context=self.context):
                continue
            self.frames += 1
            command, line = describe_frame(msg.arbitration_id, bytes(msg.data))
            twist = None
            if command is not None:  # the payload in physical units, through the profile
                twist = [round(v, 6) for v in command_velocity(command, self.robot)]
                line += f" = {twist[0]:.2f} m/s, {twist[1]:+.3f} rad/s ({self.vehicle})"
            if command is None:
                self.undecoded += 1
                self.get_logger().warning(line)
            elif self.cfg["log_every_frame"] or line != self.last_line:
                self.get_logger().info(line)
            self.last_line = line
            self.pub.publish(String(data=line))
            row = {
                "n": self.frames,
                "t": msg.timestamp,
                "id": msg.arbitration_id,
                "data": bytes(msg.data).hex(),
                "decoded": line.split(" -> ", 1)[1],
                "twist": twist,
                "ok": command is not None,
            }
            self.log.write(json.dumps(row) + "\n")

    def close(self) -> None:
        if self.bus is None:
            return
        self.running = False
        self.reader.join()
        self.get_logger().info(
            f"{self.frames} frames read, {self.frames - self.undecoded} decoded, "
            f"{self.undecoded} not a drive command"
        )
        self.log.close()
        self.bus.shutdown()


def main() -> None:
    rclpy.init()
    node = CanMonitorNode()
    try:
        if node.bus is not None:
            rclpy.spin(node)
    except (KeyboardInterrupt, ExternalShutdownException):
        pass
    finally:
        node.close()
        node.destroy_node()
        rclpy.try_shutdown()
