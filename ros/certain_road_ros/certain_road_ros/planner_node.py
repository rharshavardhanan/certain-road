"""The drive decision as a ROS node: detections in, /cmd_vel and CAN out, decision code unchanged.

Per frame, exactly the step `run_scenario` and the runtime take: `build_perception`
(corridor, escape zones, the N-of-M `Confirmer`), then `next_state`, then `command_for`.
The `Command` leaves through `RosTransport`, one more `Transport` beside `CanTransport`
(D049, D093). With `can:=auto|true` the two are fanned out together, so every decision is
also a real CAN frame on the bus `configs/ros/demo.yaml` names (vcan0 on the Jetson,
D052). Nothing in `driving/` knows it is running under ROS or which bus is attached.

**Any camera.** The image size comes from /camera/camera_info, latched by `sim_node` and
`video_node` or streamed by a Gazebo camera. Until one arrives the planner assumes the
vehicle profile's camera and says so once in the log.

**Any vehicle.** `vehicle:=` names the profile (configs/ros/demo.yaml `profiles`) that turns
each Command into /cmd_vel's m/s and rad/s: the indoor robot by default, `car` for the
Gazebo car (configs/sim/car.yaml). `corridor:=` names the corridor the frame is judged with,
by default the vehicle's own (configs/driving/corridor_car.yaml for the car, derived from the
design camera). `frame_period_s:=` sets the staleness failsafe's frame for a camera that
sends no scenario (the Gazebo camera's 1/30 s); unset, `planner.frame_period_s`.

**Staleness failsafe.** If detections stop arriving for longer than the policy's
`max_frame_age` frames, a stale `Perception` goes through the same `next_state`, whose
failsafe answers STOP. Killing the perception node mid-run stops the robot. A frame is the
sim scenario's `dt`, or `planner.frame_period_s` for a camera that sends no scenario.
A lockstep video is the exception: the recording waits for perception, so its clock is the
video's and no frame is ever late by it. A slow GPU there would read as a blind vehicle and
fill the decisions with STOPs that say nothing about the road, so the wall-clock failsafe
is off while lockstep frames arrive; `video_summary.json` reports perception's turnaround
instead. Realtime video, the sim and Gazebo keep it.

**Evidence.** Everything goes to `runs/ros/<UTC stamp>/`:

- `decisions.jsonl`, one line per decision: drive state, command, the CAN payload and,
  for a video frame, its video time and the counted potholes in view.
- `episodes.jsonl`, per sim episode: the states it reached against the scenario's
  `expect`, and whether its drive-state sequence matches `run_scenario` on the same
  scenario offline. In projection mode they should match frame for frame; a mismatch
  means ROS changed the loop's timing, which this line makes visible rather than hidden.
- `video_score.json`, at shutdown after a video: which counted potholes the planner left
  NORMAL for, and how many reactions began with none in view
  (`certain_road_ros.video.score_decisions`). Open loop: the video never swerves.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field

import rclpy
import yaml
from diagnostic_msgs.msg import DiagnosticArray
from geometry_msgs.msg import Point, Twist
from rclpy.executors import ExternalShutdownException
from rclpy.node import Node
from rclpy.qos import QoSProfile, ReliabilityPolicy
from sensor_msgs.msg import CameraInfo
from std_msgs.msg import ColorRGBA, Header, String
from vision_msgs.msg import Detection2DArray
from visualization_msgs.msg import Marker, MarkerArray

from certain_road.canbus.protocol import Command
from certain_road.driving.confirm import Confirmer
from certain_road.driving.controller import command_for
from certain_road.driving.corridor import load_corridor
from certain_road.driving.decision import DriveState, Perception, load_policy, next_state
from certain_road.driving.perceive import build_perception
from certain_road.sim.model import command_velocity, load_robot
from certain_road.sim.run import run_scenario
from certain_road.sim.scenario import SCENARIOS
from certain_road_ros.can_link import (
    FanoutTransport,
    can_transport_config,
    candump_text,
    describe_command,
    open_can,
)
from certain_road_ros.common import (
    ANY_LIVE,
    LATCHED,
    LATEST,
    StampPairer,
    demo_config,
    detections_from,
    frame_info_from,
    profile,
    repo_path,
    run_dir,
    stamp_key,
)
from certain_road_ros.transport import RosTransport
from certain_road_ros.video import FrameInfo, score_decisions

_CMD_QUEUE = 10
_INFO = "frame_info"


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
        vehicle, vehicle_path, corridor, corridor_path = profile(
            self.declare_parameter("vehicle", "").value,
            self.declare_parameter("corridor", "").value,
        )
        self.robot = load_robot(vehicle_path)
        self.corridor = load_corridor(corridor_path)
        self.policy = load_policy(repo_path("configs", "driving", "decision.yaml"))
        self.escape_lanes = float(yaml.safe_load(corridor_path.read_text())["escape_lanes"])
        self.hazard_classes = set(self.cfg["hazard_classes"])

        self.drive_state = DriveState.NORMAL
        self.confirmer = Confirmer(self.policy.required, self.policy.window)
        self.episode: Episode | None = None
        self.episodes_run = 0
        # a sim scenario sets its own; a camera without one uses this
        self.dt: float = (
            self.declare_parameter("frame_period_s", 0.0).value or self.cfg["frame_period_s"]
        )
        self.last_frame_time = None
        self.stale = False
        self.lockstep_video = False  # set by each video frame; see the docstring
        self.source = "unknown"
        self.image_size: tuple[int, int] | None = None
        self.pairer = StampPairer([_INFO], self.cfg["frame_info_cache"])
        self.video_rows: list[dict] = []
        self.gt_total: int | None = None
        self.decisions = 0
        self.stale_decisions = 0
        self.can_failures = 0

        out = run_dir(self.declare_parameter("run_stamp", "").value)
        self.log_path = out / "episodes.jsonl"
        self.score_path = out / "video_score.json"
        self.decision_log = (out / "decisions.jsonl").open("a", buffering=1)

        t = self.topics
        ros = RosTransport(self.create_publisher(Twist, t["cmd_vel"], _CMD_QUEUE), self.robot)
        can_cfg = can_transport_config(repo_path("configs", "canbus", "transport.yaml"), cfg["can"])
        mode = self.declare_parameter("can", "").value or str(cfg["can"]["enabled"]).lower()
        can, can_note = open_can(can_cfg, mode)
        self.can_id = can_cfg.arbitration_id if can else None
        self.transport = ros if can is None else FanoutTransport([ros, can], self._can_failed)
        (self.get_logger().info if can else self.get_logger().warning)(can_note)

        self.pub_state = self.create_publisher(String, t["drive_state"], LATEST)
        self.pub_markers = self.create_publisher(MarkerArray, t["planner_markers"], LATEST)
        # frame_info before detections: when both are queued, the frame's facts go first
        info_qos = QoSProfile(
            depth=self.cfg["frame_info_cache"], reliability=ReliabilityPolicy.RELIABLE
        )
        self.create_subscription(DiagnosticArray, t["frame_info"], self._on_frame_info, info_qos)
        self.create_subscription(Detection2DArray, t["detections"], self._on_detections, LATEST)
        self.create_subscription(String, t["scenario"], self._on_scenario, LATCHED)
        self.create_subscription(String, t["source"], self._on_source, LATCHED)
        # Latched (sim_node, video_node) and streamed (a Gazebo bridge) camera_info alike.
        for qos in (LATCHED, ANY_LIVE):
            self.create_subscription(CameraInfo, t["camera_info"], self._on_camera_info, qos)
        self.create_timer(self.cfg["watchdog_period_s"], self._watchdog)
        self.get_logger().info(
            f"vehicle {vehicle} ({vehicle_path.name}: {self.robot.max_speed_mps} m/s, wheelbase "
            f"{self.robot.wheelbase_m} m, steer {self.robot.max_steer_rad} rad); corridor "
            f"{corridor} ({corridor_path.name}); staleness frame {self.dt:.4f} s; logs: {out}"
        )

    # ---- inputs beside the detections ------------------------------------------------

    def _on_camera_info(self, msg: CameraInfo) -> None:
        size = (int(msg.width), int(msg.height))
        if size != self.image_size:
            self.image_size = size
            self.get_logger().info(f"image size {size[0]}x{size[1]} from {msg.header.frame_id}")

    def _size(self) -> tuple[int, int]:
        if self.image_size is not None:
            return self.image_size
        cam = self.robot.camera
        self.get_logger().warning(
            f"no {self.topics['camera_info']} yet: assuming the simulated camera's "
            f"{cam.img_w}x{cam.img_h} (configs/sim/robot.yaml). Boxes from any other camera "
            "would be judged against the wrong frame size.",
            once=True,
        )
        return cam.img_w, cam.img_h

    def _on_frame_info(self, msg: DiagnosticArray) -> None:
        for dets, companions in self.pairer.add_companion(_INFO, stamp_key(msg.header.stamp), msg):
            self._judge(dets, companions)

    def _can_failed(self, transport: object, exc: Exception) -> None:
        self.can_failures += 1
        self.get_logger().error(f"CAN send failed, /cmd_vel unaffected: {exc}", once=True)

    # ---- the decision, per frame -----------------------------------------------------

    def _on_detections(self, msg: Detection2DArray) -> None:
        """While a video is playing, a frame's detections wait for its /video/frame_info,
        which was sent before the frame itself: the decision is the same either way, only
        its log line gains the video time. Any other camera is judged at once."""
        needs = {_INFO} if self.count_publishers(self.topics["frame_info"]) > 0 else set()
        for dets, companions in self.pairer.add_primary(stamp_key(msg.header.stamp), msg, needs):
            self._judge(dets, companions)

    def _judge(self, msg: Detection2DArray, companions: dict) -> None:
        img_w, img_h = self._size()
        dets = [
            d for d in detections_from(msg, img_w, img_h) if d.class_name in self.hazard_classes
        ]
        perception, _ = build_perception(
            dets, self.corridor, self.confirmer, escape_lanes=self.escape_lanes
        )
        info = frame_info_from(companions[_INFO]) if _INFO in companions else None
        self.lockstep_video = info is not None and info.lockstep
        self._decide(perception, msg.header.stamp, info, len(dets))
        self.last_frame_time = self.get_clock().now()
        if self.stale:
            self.stale = False
            self.get_logger().info("detections resumed")
        if self.episode is not None:
            self.episode.states.append(str(self.drive_state))

    def _watchdog(self) -> None:
        if self.last_frame_time is None or self.lockstep_video:
            return
        age_s = (self.get_clock().now() - self.last_frame_time).nanoseconds / 1e9
        frame_age = int(age_s / self.dt)
        if frame_age <= self.policy.max_frame_age:
            return
        stale = Perception(
            hazard=None, left_blocked=False, right_blocked=False, frame_age=frame_age, healthy=True
        )
        self._decide(stale)
        self.stale_decisions += 1
        if self.episode is not None:
            self.episode.stale_stops += 1
        if not self.stale:
            self.stale = True
            self.get_logger().warning(
                f"no detections for {frame_age} frames (> max_frame_age "
                f"{self.policy.max_frame_age}): failsafe -> {self.drive_state}"
            )

    def _decide(
        self,
        perception: Perception,
        stamp=None,
        info: FrameInfo | None = None,
        hazards: int | None = None,
    ) -> None:
        before = self.drive_state
        self.drive_state = next_state(self.drive_state, perception, self.policy)
        command = command_for(self.drive_state, self.policy)
        self.transport.send(command)
        self.pub_state.publish(String(data=str(self.drive_state)))
        self.pub_markers.publish(self._marker())
        self._record(before, command, stamp, info, hazards)

    def _record(self, before, command: Command, stamp, info: FrameInfo | None, hazards) -> None:
        """One line of decisions.jsonl; a log line when the state changes."""
        self.decisions += 1
        payload = command.to_bytes()
        row = {
            "n": self.decisions,
            "wall_s": self.get_clock().now().nanoseconds / 1e9,
            "stamp": list(stamp_key(stamp)) if stamp is not None else None,
            "trigger": "frame" if stamp is not None else "stale",
            "state": str(self.drive_state),
            "command": describe_command(command),
            # the Twist RosTransport sent: m/s and rad/s through the vehicle profile
            "twist": [round(v, 6) for v in command_velocity(command, self.robot)],
            "payload": payload.hex(),
            "can": candump_text(self.can_id, payload) if self.can_id is not None else None,
            "hazards": hazards,
        }
        if info is not None:
            row |= {
                "frame": info.frame,
                "video_time_s": info.video_time_s,
                "gt_in_view": list(info.gt_in_view),
            }
            self.gt_total = info.gt_total
            self.video_rows.append(row)
        self.decision_log.write(json.dumps(row) + "\n")
        if self.drive_state != before:
            where = ""
            if info is not None:
                where = f"t {info.video_time_s:7.2f} s, frame {info.frame}, {info.strip}: "
            can = f"  CAN {row['can']}" if row["can"] else ""
            self.get_logger().info(f"{where}{before} -> {self.drive_state}{can}")

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

    def finish_video(self) -> dict | None:
        """Score the video's decisions against its ground truth, once, at shutdown."""
        if not self.video_rows:
            return None
        score = score_decisions(self.video_rows, self.gt_total)
        score |= {
            "open_loop": "a recording cannot be steered: decisions only, nothing avoided",
            "source": self.source,
            "decisions": self.decisions,
            "stale_decisions": self.stale_decisions,
            "can_frames_sent": self.decisions - self.can_failures if self.can_id else 0,
            "can_send_failures": self.can_failures,
        }
        self.score_path.write_text(json.dumps(score, indent=1))
        return score

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

    def close(self) -> None:
        self.transport.close()
        self.decision_log.close()


def main() -> None:
    rclpy.init()
    node = PlannerNode()
    try:
        rclpy.spin(node)
    except (KeyboardInterrupt, ExternalShutdownException):
        pass
    finally:
        node.finish_episode(complete=False)
        score = node.finish_video()
        if score is not None:
            node.get_logger().info(
                f"video score over {score['frames']} frames: of the "
                f"{score['gt_potholes_in_processed_frames']} counted potholes in view "
                f"({score['gt_potholes']} in the ground truth), "
                f"{score['gt_potholes_left_normal']} saw the planner leave NORMAL "
                f"({score['gt_potholes_manoeuvred']} with a manoeuvre); "
                f"{score['reaction_onsets_outside_gt']} of {score['reaction_onsets']} reaction "
                f"onsets and {score['manoeuvre_onsets_outside_gt']} of "
                f"{score['manoeuvre_onsets']} manoeuvre onsets had no counted pothole in view. "
                f"{node.score_path}"
            )
        node.close()
        node.destroy_node()
        rclpy.try_shutdown()
