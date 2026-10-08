"""ROS 2 as one more `Transport` (D049, D050, D093): a `Command` leaves as /cmd_vel.

The planner node hands each `Command` to `RosTransport.send` exactly as the runtime
hands one to `CanTransport`, so `driving/` cannot tell which it is talking to. ROS is a
change of transport, not a fork of the decision logic.

The Twist carries physical units, as /cmd_vel does across ROS: `linear.x` in m/s and
`angular.z` the yaw rate in rad/s, from `certain_road.sim.model.command_velocity`. The
simulated vehicle reads it back with `twist_command` and drives it through `step`.

This lives here, not in `certain_road.canbus`, because it needs rclpy and the package's
CI has no ROS.
"""

from __future__ import annotations

from geometry_msgs.msg import Twist
from rclpy.publisher import Publisher

from certain_road.canbus.protocol import Command
from certain_road.canbus.transport import Transport
from certain_road.sim.model import Robot, command_from_velocity, command_velocity


class RosTransport(Transport):
    """Publishes each `Command` as a Twist on the publisher it was given."""

    def __init__(self, publisher: Publisher, robot: Robot) -> None:
        self._publisher = publisher
        self._robot = robot

    def send(self, command: Command) -> None:
        linear, yaw_rate = command_velocity(command, self._robot)
        msg = Twist()
        msg.linear.x = linear
        msg.angular.z = yaw_rate
        self._publisher.publish(msg)


def twist_command(msg: Twist, robot: Robot) -> Command:
    """What the vehicle receives: the inverse of `RosTransport.send`."""
    return command_from_velocity(msg.linear.x, msg.angular.z, robot)
