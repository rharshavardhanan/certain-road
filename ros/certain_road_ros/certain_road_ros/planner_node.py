"""The drive decision as a ROS node: detections in, /cmd_vel out, decision code unchanged.

Per frame, exactly the step `run_scenario` and the runtime take: `build_perception`
(corridor, escape zones, the N-of-M `Confirmer`), then `next_state`, then `command_for`.
The `Command` leaves through `RosTransport`, one more `Transport` beside `CanTransport`
(D049, D093). Nothing in `driving/` knows it is running under ROS.

**Staleness failsafe.** If detections stop arriving for longer than the policy's
`max_frame_age` frames, a stale `Perception` goes through the same `next_state`, whose
failsafe answers STOP. Killing the perception node mid-run stops the robot.

**Evidence, per episode.** When the sim starts a new scenario, the finished episode is
written to `runs/ros/<UTC stamp>/episodes.jsonl`: the states it reached against the
scenario's `expect`, and whether its drive-state sequence matches `run_scenario` on the
same scenario offline. In projection mode they should match frame for frame; a mismatch
means ROS changed the loop's timing, which this line makes visible rather than hidden.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import UTC, datetime

import rclpy
import yaml
from geometry_msgs.msg import Point, Twist
from rclpy.executors import ExternalShutdownException
from rclpy.node import Node
from std_msgs.msg import ColorRGBA, Header, String
from vision_msgs.msg import Detection2DArray
from visualization_msgs.msg import Marker, MarkerArray

from certain_road.driving.confirm import Confirmer
from certain_road.driving.controller import command_for
from certain_road.driving.corridor import CORRIDOR_CONFIG_PATH, load_corridor
from certain_road.driving.decision import DriveState, Perception, load_policy, next_state
from certain_road.driving.perceive import build_perception
from certain_road.sim.model import load_robot
from certain_road.sim.run import run_scenario
from certain_road.sim.scenario import SCENARIOS
from certain_road_ros.common import LATCHED, LATEST, demo_config, detections_from, repo_path
from certain_road_ros.transport import RosTransport

_CMD_QUEUE = 10


@dataclass
class Episode:
    index: int
    scenario: str
    states: list[str] = field(default_factory=list)
    stale_stops: int = 0


class PlannerNode(Node):
    def __init__(self) -> None:
        super().__init__("planner_node")
        cfg = demo_config()
        self.cfg, self.topics, self.frames = cfg["planner"], cfg["topics"], cfg["frames"]
        self.robot = load_robot(repo_path("configs", "sim", "robot.yaml"))
        self.corridor = load_corridor(CORRIDOR_CONFIG_PATH)
        self.policy = load_policy(repo_path("configs", "driving", "decision.yaml"))
        self.escape_lanes = float(yaml.safe_load(CORRIDOR_CONFIG_PATH.read_text())["escape_lanes"])
        self.hazard_classes = set(self.cfg["hazard_classes"])

        self.drive_state = DriveState.NORMAL
        self.confirmer = Confirmer(self.policy.required, self.policy.window)
        self.episode: Episode | None = None
        self.episodes_run = 0
        self.dt: float | None = None
        self.last_frame_time = None
        self.stale = False
        self.source = "unknown"

        stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
        self.log_path = repo_path(self.cfg["log_dir"], stamp, "episodes.jsonl")
        self.log_path.parent.mkdir(parents=True, exist_ok=True)

        t = self.topics
        self.transport = RosTransport(
            self.create_publisher(Twist, t["cmd_vel"], _CMD_QUEUE), self.robot
        )
        self.pub_state = self.create_publisher(String, t["drive_state"], LATEST)
        self.pub_markers = self.create_publisher(MarkerArray, t["planner_markers"], LATEST)
        self.create_subscription(Detection2DArray, t["detections"], self._on_detections, LATEST)
        self.create_subscription(String, t["scenario"], self._on_scenario, LATCHED)
        self.create_subscription(String, t["source"], self._on_source, LATCHED)
        self.create_timer(self.cfg["watchdog_period_s"], self._watchdog)
        self.get_logger().info(f"episode log: {self.log_path}")

    # ---- the decision, per frame -----------------------------------------------------

    def _on_detections(self, msg: Detection2DArray) -> None:
        cam = self.robot.camera
        dets = [
            d
            for d in detections_from(msg, cam.img_w, cam.img_h)
            if d.class_name in self.hazard_classes
        ]
        perception, _ = build_perception(
            dets, self.corridor, self.confirmer, escape_lanes=self.escape_lanes
        )
        self._decide(perception)
        self.last_frame_time = self.get_clock().now()
        if self.stale:
            self.stale = False
            self.get_logger().info("detections resumed")
        if self.episode is not None:
            self.episode.states.append(str(self.drive_state))

    def _watchdog(self) -> None:
        if self.dt is None or self.last_frame_time is None:
            return
        age_s = (self.get_clock().now() - self.last_frame_time).nanoseconds / 1e9
        frame_age = int(age_s / self.dt)
        if frame_age <= self.policy.max_frame_age:
            return
        stale = Perception(
            hazard=None, left_blocked=False, right_blocked=False, frame_age=frame_age, healthy=True
        )
        self._decide(stale)
        if self.episode is not None:
            self.episode.stale_stops += 1
        if not self.stale:
            self.stale = True
            self.get_logger().warning(
                f"no detections for {frame_age} frames (> max_frame_age "
                f"{self.policy.max_frame_age}): failsafe -> {self.drive_state}"
            )

    def _decide(self, perception: Perception) -> None:
        self.drive_state = next_state(self.drive_state, perception, self.policy)
        self.transport.send(command_for(self.drive_state, self.policy))
        self.pub_state.publish(String(data=str(self.drive_state)))
        self.pub_markers.publish(self._marker())

    # ---- episodes --------------------------------------------------------------------

    def _on_source(self, msg: String) -> None:
        self.source = msg.data

    def _on_scenario(self, msg: String) -> None:
        self.finish_episode(complete=True)
        name = msg.data
        self.dt = SCENARIOS[name].dt
        self.drive_state = DriveState.NORMAL
        self.confirmer.reset()
        self.last_frame_time = self.get_clock().now()
        self.episode = Episode(self.episodes_run, name)
        self.episodes_run += 1

    def finish_episode(self, *, complete: bool) -> None:
        ep = self.episode
        if ep is None or not ep.states:
            return
        scenario = SCENARIOS[ep.scenario]
        offline = run_scenario(scenario, self.robot, self.corridor, self.policy).drive_state
        seen = set(ep.states)
        reached = scenario.expect in seen and (ep.scenario != "clear" or seen == {"normal"})
        diverge = next(
            (i for i, (a, b) in enumerate(zip(ep.states, offline, strict=False)) if a != b),
            None,
        )
        row = {
            "episode": ep.index,
            "scenario": ep.scenario,
            "complete": complete,
            "source": self.source,
            "expect": scenario.expect,
            "states_seen": sorted(seen),
            "reached_expect": reached,
            "frames": len(ep.states),
            "offline_frames": len(offline),
            # a run stopped mid-episode is judged on the frames it reached
            "matches_offline": ep.states == (offline if complete else offline[: len(ep.states)]),
            "first_divergence": diverge,
            "stale_stops": ep.stale_stops,
            "states": ep.states,
        }
        with self.log_path.open("a") as f:
            f.write(json.dumps(row) + "\n")
        verdict = "PASS" if reached else "FAIL"
        match = "matches offline run" if row["matches_offline"] else f"differs at {diverge}"
        self.get_logger().info(
            f"episode {ep.index} '{ep.scenario}': {verdict} (expect {scenario.expect}, "
            f"saw {sorted(seen)}); {len(ep.states)} frames, {match}"
        )
        self.episode = None

    def _marker(self) -> MarkerArray:
        cfg = self.cfg
        # Stamp zero and frame_locked: RViz draws it on the latest robot transform. Stamped
        # "now" it would be newer than any TF the sim has sent, and could not be placed.
        m = Marker(
            header=Header(frame_id=self.frames["robot"]),
            frame_locked=True,
            ns="drive_state",
            id=0,
            type=Marker.TEXT_VIEW_FACING,
            action=Marker.ADD,
            text=str(self.drive_state).upper(),
        )
        m.pose.position = Point(x=0.0, y=0.0, z=cfg["text_z_m"])
        m.scale.z = cfg["text_height_m"]
        r, g, b, a = cfg["state_rgba"][str(self.drive_state)]
        m.color = ColorRGBA(r=r, g=g, b=b, a=a)
        return MarkerArray(markers=[m])


def main() -> None:
    rclpy.init()
    node = PlannerNode()
    try:
        rclpy.spin(node)
    except (KeyboardInterrupt, ExternalShutdownException):
        pass
    finally:
        node.finish_episode(complete=False)
        node.destroy_node()
        rclpy.try_shutdown()
