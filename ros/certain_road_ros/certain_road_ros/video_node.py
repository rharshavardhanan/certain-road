"""A road video as the camera: frames on /camera/image_raw, open loop.

Plays a clip (`video:=`, default the RT Dashcam clip `2DV-cYmIvT4`, CC BY) into the same
graph `sim_node` drives: /camera/image_raw (bgr8, the clip's own size), /camera/camera_info
(latched; the size, and no intrinsics, since downloaded footage has no camera model), and
per frame, with the image's stamp, /video/frame_info: the frame's video time and which of
the hand-counted potholes are in view (`configs/eval/video.yaml`, `live`). Perception
draws that as the ground-truth strip; the planner logs every decision with its video time.

**Open loop.** A recording cannot be steered. The planner decides on every frame and its
commands go out as /cmd_vel and CAN frames, but the next frame is the next frame of the
recording whatever was decided. The overlay and the logs say so.

**Pacing.**

- `lockstep` (default): the next frame goes out only once the detections for the last one
  are back. Every frame is processed, so the planner's 3-of-5 confirmation sees the clip's
  30 fps, the rate D075 and D088 set it at. Plays slower than real time.
- `realtime`: frames go out at the clip's rate by the wall clock. Perception keeps only the
  newest, so frames are dropped whenever the GPU falls behind, and 3-of-5 then spans more
  than 0.1 s of road. The overlay labels it; the summary counts the drops.

The window defaults to the ground truth's 120-180 s; any other clip plays whole with no
ground truth. At the end the node writes `runs/ros/<stamp>/video_summary.json` and exits
(the launch file then stops the graph), or loops with `loop:=true`.
"""

from __future__ import annotations

import json
import time
from collections import OrderedDict
from pathlib import Path

import cv2
import rclpy
import yaml
from diagnostic_msgs.msg import DiagnosticArray
from geometry_msgs.msg import TransformStamped
from rclpy.executors import ExternalShutdownException
from rclpy.node import Node
from rclpy.qos import QoSProfile, ReliabilityPolicy
from sensor_msgs.msg import CameraInfo, Image
from std_msgs.msg import Header
from tf2_ros import StaticTransformBroadcaster
from vision_msgs.msg import Detection2DArray

from certain_road_ros.common import (
    LATCHED,
    LATEST,
    camera_info_msg,
    demo_config,
    frame_info_msg,
    image_msg,
    repo_path,
    run_dir,
    stamp_key,
)
from certain_road_ros.video import FrameInfo, in_view, read_intervals

PACINGS = ("lockstep", "realtime")
_TRUE = ("true", "1", "yes")


def resolve(path: str) -> Path:
    """As given if it exists from here, else relative to the repository."""
    p = Path(path).expanduser()
    return p if p.is_absolute() or p.exists() else repo_path(path)


class VideoNode(Node):
    def __init__(self) -> None:
        super().__init__("video_node")
        cfg = demo_config()
        self.cfg, self.topics, self.frames = cfg["video"], cfg["topics"], cfg["frames"]
        live = yaml.safe_load(repo_path("configs", "eval", "video.yaml").read_text())["live"]

        def text(name: str) -> str:
            return str(self.declare_parameter(name, "").value)

        self.clip = resolve(text("video") or self.cfg["clip"])
        self.pacing = text("pacing") or self.cfg["pacing"]
        if self.pacing not in PACINGS:
            raise ValueError(f"pacing must be one of {PACINGS}, got {self.pacing!r}")
        loop = text("loop")
        self.loop = loop.lower() in _TRUE if loop else bool(self.cfg["loop"])
        self.out_dir = run_dir(text("run_stamp"))

        self.cap = cv2.VideoCapture(str(self.clip))
        if not self.cap.isOpened():
            raise FileNotFoundError(f"cannot open video {self.clip}")
        self.fps = self.cap.get(cv2.CAP_PROP_FPS)
        n_frames = int(self.cap.get(cv2.CAP_PROP_FRAME_COUNT))
        self.width = int(self.cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        self.height = int(self.cap.get(cv2.CAP_PROP_FRAME_HEIGHT))

        if self.clip.stem == self.cfg["gt_clip_stem"]:
            self.gt_path = repo_path(live["gt"])
            self.intervals = read_intervals(self.gt_path)
            window, self.credit = live["window_s"], live["credit"]
        else:
            self.gt_path, self.intervals, self.credit = None, None, ""
            window = [0.0, n_frames / self.fps]
        start, end = text("start"), text("end")
        self.start_s = float(start) if start else float(window[0])
        self.end_s = float(end) if end else float(window[1])
        self.first = round(self.start_s * self.fps)
        self.last = min(round(self.end_s * self.fps), n_frames)
        if not self.first < self.last:
            raise ValueError(f"empty window {self.start_s}-{self.end_s} s in {self.clip.name}")

        t = self.topics
        self.pub_image = self.create_publisher(Image, t["image"], LATEST)
        self.pub_cam = self.create_publisher(CameraInfo, t["camera_info"], LATCHED)
        info_qos = QoSProfile(
            depth=cfg["perception"]["frame_info_queue"], reliability=ReliabilityPolicy.RELIABLE
        )
        self.pub_info = self.create_publisher(DiagnosticArray, t["frame_info"], info_qos)
        self.create_subscription(Detection2DArray, t["detections"], self._on_detections, LATEST)
        header = Header(stamp=self.get_clock().now().to_msg(), frame_id=self.frames["camera"])
        self.pub_cam.publish(camera_info_msg(self.width, self.height, header))
        # RViz needs its fixed frame to exist. A recording has no pose: the camera is pinned
        # at the world origin, and nothing is drawn in 3D.
        self.static_tf = StaticTransformBroadcaster(self)
        mount = TransformStamped(header=Header(stamp=header.stamp, frame_id=self.frames["world"]))
        mount.child_frame_id = self.frames["camera"]
        mount.transform.rotation.w = 1.0
        self.static_tf.sendTransform(mount)

        self.done = False
        self.connected_at: float | None = None
        self.started = False
        self.next_index = self.first
        self.sent: OrderedDict = OrderedDict()  # stamp -> send time, recent frames only
        self.turnaround: list[float] = []  # frame sent -> its detections back, seconds
        self.waiting: tuple | None = None
        self.sent_at = 0.0
        self.t0 = 0.0
        self.counts = {"published": 0, "processed": 0, "skipped_at_source": 0, "timeouts": 0}
        self.cap.set(cv2.CAP_PROP_POS_FRAMES, self.first)
        self.create_timer(1.0 / self.fps, self._tick)

        gt = f"ground truth {self.gt_path.name}" if self.gt_path else "no ground truth"
        self.get_logger().info(
            f"{self.clip.name}: {self.width}x{self.height} @ {self.fps:.0f} fps, window "
            f"{self.start_s:.1f}-{self.end_s:.1f} s ({self.last - self.first} frames), "
            f"{self.pacing}, {gt}. OPEN LOOP: a recording cannot be steered."
        )
        self.get_logger().info("waiting for perception_node and planner_node")

    # ---- start, pace, stop -----------------------------------------------------------

    def _connected(self) -> bool:
        """Perception reads frames and publishes detections, and the planner is up."""
        t = self.topics
        return (
            self.count_subscribers(t["image"]) > 0
            and self.count_publishers(t["detections"]) > 0
            and self.count_publishers(t["cmd_vel"]) > 0
        )

    def _tick(self) -> None:
        if self.done:
            return
        now = time.monotonic()
        if not self.started:
            if self.connected_at is None:
                if self._connected():
                    self.connected_at = now
                return
            if now - self.connected_at < self.cfg["start_delay_s"]:
                return
            self.started, self.t0 = True, now
            self.get_logger().info(f"graph connected: playing frame {self.first}")
            if self.pacing == "lockstep":
                self._send_next()
            return
        if self.pacing == "realtime":
            target = self.first + int((now - self.t0) * self.fps)
            if target >= self.last:
                self._finish()
                return
            while self.next_index < target:  # the clock moved past these: never sent
                self.cap.grab()
                self.next_index += 1
                self.counts["skipped_at_source"] += 1
            if self.next_index == target:
                self._send_next()
        elif self.waiting is not None and now - self.sent_at > self.cfg["lockstep_timeout_s"]:
            self.counts["timeouts"] += 1
            self.get_logger().warning(
                f"no detections for frame {self.next_index - 1} in "
                f"{self.cfg['lockstep_timeout_s']} s: sending the next frame"
            )
            self._send_next()

    def _on_detections(self, msg: Detection2DArray) -> None:
        key = stamp_key(msg.header.stamp)
        if key not in self.sent:
            return  # not one of this node's frames
        self.counts["processed"] += 1
        self.turnaround.append(time.monotonic() - self.sent[key])
        if self.pacing == "lockstep" and key == self.waiting:
            self._send_next()

    def _send_next(self) -> None:
        if self.next_index >= self.last:
            self._finish()
            return
        ok, bgr = self.cap.read()
        if not ok:
            self.get_logger().warning(f"the video ended at frame {self.next_index}")
            self._finish()
            return
        n, t_s = self.next_index, self.next_index / self.fps
        header = Header(stamp=self.get_clock().now().to_msg(), frame_id=self.frames["camera"])
        info = FrameInfo(
            clip=self.clip.stem,
            frame=n,
            video_time_s=t_s,
            gt_in_view=in_view(self.intervals, t_s) if self.intervals is not None else (),
            gt_total=len(self.intervals) if self.intervals is not None else None,
            pacing=self.cfg["pacing_label"][self.pacing],
            lockstep=self.pacing == "lockstep",
            notice=self.cfg["notice"],
            credit=self.credit,
        )
        key = stamp_key(header.stamp)
        self.sent[key] = time.monotonic()
        while len(self.sent) > self.cfg["sent_memory"]:
            self.sent.popitem(last=False)
        self.pub_info.publish(frame_info_msg(info, header))  # before the image it describes
        self.pub_image.publish(image_msg(bgr, header, "bgr8"))
        self.waiting, self.sent_at = key, time.monotonic()
        self.next_index += 1
        self.counts["published"] += 1

    def _finish(self) -> None:
        wall = time.monotonic() - self.t0
        c = self.counts
        played_s = (self.next_index - self.first) / self.fps
        summary = {
            "clip": str(self.clip.name),
            "pacing": self.pacing,
            "window_s": [self.start_s, self.end_s],
            "video_fps": self.fps,
            "size": [self.width, self.height],
            "ground_truth": self.gt_path.name if self.gt_path else None,
            "frames_in_window": self.last - self.first,
            "frames_published": c["published"],
            "frames_processed": c["processed"],
            "frames_skipped_at_source": c["skipped_at_source"],
            "frames_dropped_by_perception": c["published"] - c["processed"],
            "lockstep_timeouts": c["timeouts"],
            # frame sent -> its detections back: perception's time, the GPU's and the bus's
            "turnaround_s": _spread(self.turnaround),
            "wall_s": round(wall, 2),
            "processed_fps": round(c["processed"] / wall, 2) if wall else None,
            "real_time_factor": round(played_s / wall, 3) if wall else None,
            "open_loop": "a recording cannot be steered: decisions only, nothing avoided",
        }
        (self.out_dir / "video_summary.json").write_text(json.dumps(summary, indent=1))
        self.get_logger().info(
            f"window done: {c['processed']} of {self.last - self.first} frames processed "
            f"({c['published']} sent, {c['skipped_at_source']} skipped at source, "
            f"{c['timeouts']} timeouts) in {wall:.1f} s = {summary['processed_fps']} fps, "
            f"{summary['real_time_factor']}x real time. {self.out_dir / 'video_summary.json'}"
        )
        if self.loop:
            self.cap.set(cv2.CAP_PROP_POS_FRAMES, self.first)
            self.next_index, self.t0, self.waiting = self.first, time.monotonic(), None
            self.counts = dict.fromkeys(self.counts, 0)
            self.turnaround = []
            if self.pacing == "lockstep":
                self._send_next()
            return
        self.done = True


def _spread(values: list[float]) -> dict | None:
    if not values:
        return None
    v = sorted(values)
    return {
        "median": round(v[len(v) // 2], 4),
        "p99": round(v[min(len(v) - 1, int(len(v) * 0.99))], 4),
        "max": round(v[-1], 4),
    }


def main() -> None:
    rclpy.init()
    node = VideoNode()
    try:
        while rclpy.ok() and not node.done:
            rclpy.spin_once(node)
    except (KeyboardInterrupt, ExternalShutdownException):
        pass
    finally:
        node.cap.release()
        node.destroy_node()
        rclpy.try_shutdown()
