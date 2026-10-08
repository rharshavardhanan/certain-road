"""What the nodes share: the demo config, QoS profiles, message conversions and pairing.

Conversions and plumbing only. No node logic lives here, so each node file reads as its
own composition root.
"""

from __future__ import annotations

import array
import math
from collections import OrderedDict
from datetime import UTC, datetime
from functools import cache
from pathlib import Path

import numpy as np
import yaml
from builtin_interfaces.msg import Time
from diagnostic_msgs.msg import DiagnosticArray, DiagnosticStatus, KeyValue
from geometry_msgs.msg import Quaternion
from rclpy.qos import DurabilityPolicy, QoSProfile, ReliabilityPolicy
from sensor_msgs.msg import CameraInfo, Image
from std_msgs.msg import Header
from vision_msgs.msg import Detection2D, Detection2DArray, ObjectHypothesisWithPose

from certain_road.artifacts.schema import Detection
from certain_road.core.paths import repo_root
from certain_road_ros.video import FrameInfo

# Late joiners (RViz, a restarted planner) get the last value: scenario and source.
LATCHED = QoSProfile(
    depth=1,
    durability=DurabilityPolicy.TRANSIENT_LOCAL,
    reliability=ReliabilityPolicy.RELIABLE,
)
# Keep only the newest frame: a slow consumer skips frames rather than falling behind.
LATEST = QoSProfile(depth=1, reliability=ReliabilityPolicy.RELIABLE)
# Matches any publisher, reliable or best effort, latched or not, but replays no history. A
# camera that streams camera_info with every frame (a Gazebo bridge) arrives this way; a
# latched one (sim_node, video_node) arrives through LATCHED.
ANY_LIVE = QoSProfile(
    depth=1,
    durability=DurabilityPolicy.VOLATILE,
    reliability=ReliabilityPolicy.BEST_EFFORT,
)

_CHANNELS = 3
_FRAME_INFO_NAME = "video"


def repo_path(*parts: str) -> Path:
    return repo_root().joinpath(*parts)


@cache
def demo_config() -> dict:
    return yaml.safe_load(repo_path("configs", "ros", "demo.yaml").read_text())


def profile(vehicle: str = "", corridor: str = "") -> tuple[str, Path, str, Path]:
    """(vehicle, its profile file, corridor, its file) from configs/ros/demo.yaml `profiles`.

    An empty vehicle is the default (the indoor robot); an empty corridor is the vehicle's
    own. An unknown name raises: a wrong profile must not drive silently."""
    p = demo_config()["profiles"]
    vehicle = vehicle or p["default"]
    corridor = corridor or vehicle
    if vehicle not in p["vehicles"]:
        raise ValueError(f"vehicle must be one of {sorted(p['vehicles'])}, got {vehicle!r}")
    if corridor not in p["corridors"]:
        raise ValueError(f"corridor must be one of {sorted(p['corridors'])}, got {corridor!r}")
    return (
        vehicle,
        repo_path(p["vehicles"][vehicle]),
        corridor,
        repo_path(p["corridors"][corridor]),
    )


def run_dir(stamp: str = "") -> Path:
    """`runs/ros/<stamp>/`, made if needed. The launch files pass one stamp to every node so
    a run's logs share a folder; a node started on its own takes the current UTC time."""
    stamp = stamp or datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    out = repo_path(demo_config()["planner"]["log_dir"], stamp)
    out.mkdir(parents=True, exist_ok=True)
    return out


def stamp_key(stamp: Time) -> tuple[int, int]:
    return (stamp.sec, stamp.nanosec)


class StampPairer:
    """Pairs each primary message (a frame) with companions carrying the same stamp.

    `add_primary` names the companions that frame needs, decided when it arrives (a
    companion topic with no publisher is not waited for). The frame is released, with its
    companions, as soon as all of them are in, whichever arrives last. At most `depth`
    frames wait and `depth` messages per companion are kept; the oldest go first, as in
    message_filters' TimeSynchronizer.
    """

    def __init__(self, companions: list[str], depth: int) -> None:
        self.depth = depth
        self._have: dict[str, OrderedDict] = {c: OrderedDict() for c in companions}
        self._waiting: OrderedDict = OrderedDict()

    def add_companion(self, name: str, key: tuple, msg: object) -> list[tuple]:
        held = self._have[name]
        held[key] = msg
        while len(held) > self.depth:
            held.popitem(last=False)
        return self._release(key)

    def add_primary(self, key: tuple, msg: object, needs: set[str]) -> list[tuple]:
        self._waiting[key] = (msg, frozenset(needs))
        while len(self._waiting) > self.depth:
            self._waiting.popitem(last=False)
        return self._release(key)

    def _release(self, key: tuple) -> list[tuple]:
        """[(primary, {companion: msg})] for the frame at `key` once it has what it needs.
        Companions it did not wait for come along if they are already in."""
        if key not in self._waiting:
            return []
        msg, needs = self._waiting[key]
        if any(key not in self._have[c] for c in needs):
            return []
        del self._waiting[key]
        return [(msg, {c: held.pop(key) for c, held in self._have.items() if key in held})]


def camera_info_msg(
    width: int, height: int, header: Header, hfov_rad: float | None = None
) -> CameraInfo:
    """The image size, and pinhole intrinsics when the camera has them.

    With `hfov_rad` (the simulated camera, square pixels, principal point at the centre, as
    `certain_road.sim.project` assumes) K and P are filled in. Without it (a downloaded
    video: no camera model) K stays all zeros, which ROS reads as "uncalibrated"."""
    msg = CameraInfo(header=header, width=width, height=height, distortion_model="plumb_bob")
    msg.d = [0.0] * 5
    msg.r = [1.0, 0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0, 1.0]
    if hfov_rad is not None:
        f = (width / 2.0) / math.tan(hfov_rad / 2.0)
        cx, cy = width / 2.0, height / 2.0
        msg.k = [f, 0.0, cx, 0.0, f, cy, 0.0, 0.0, 1.0]
        msg.p = [f, 0.0, cx, 0.0, 0.0, f, cy, 0.0, 0.0, 0.0, 1.0, 0.0]
    return msg


def frame_info_msg(info: FrameInfo, header: Header) -> DiagnosticArray:
    """A `FrameInfo` as a stamped DiagnosticArray: one status, its message the strip text,
    its level WARN while a counted pothole is in view, so `ros2 topic echo` and rqt's
    monitor read it too. No custom message type, so no extra build step."""
    status = DiagnosticStatus(
        level=DiagnosticStatus.WARN if info.gt_in_view else DiagnosticStatus.OK,
        name=_FRAME_INFO_NAME,
        message=info.strip,
        hardware_id=info.clip,
        values=[KeyValue(key=k, value=v) for k, v in info.to_values().items()],
    )
    return DiagnosticArray(header=header, status=[status])


def frame_info_from(msg: DiagnosticArray) -> FrameInfo | None:
    for status in msg.status:
        if status.name == _FRAME_INFO_NAME:
            return FrameInfo.from_values({kv.key: kv.value for kv in status.values})
    return None


def yaw_quaternion(yaw: float) -> Quaternion:
    return Quaternion(x=0.0, y=0.0, z=math.sin(yaw / 2.0), w=math.cos(yaw / 2.0))


def pitch_quaternion(pitch: float) -> Quaternion:
    """Rotation about +y. Positive pitches the nose down, as the camera's pitch_rad does."""
    return Quaternion(x=0.0, y=math.sin(pitch / 2.0), z=0.0, w=math.cos(pitch / 2.0))


def image_msg(pixels: np.ndarray, header: Header, encoding: str) -> Image:
    """An (H, W, 3) uint8 array as an Image. `encoding` is rgb8 or bgr8, as the array is."""
    if encoding not in {"rgb8", "bgr8"}:
        raise ValueError(f"unsupported encoding {encoding!r}")
    h, w, c = pixels.shape
    if c != _CHANNELS or pixels.dtype != np.uint8:
        raise ValueError(f"expected (H, W, 3) uint8, got {pixels.shape} {pixels.dtype}")
    data = array.array("B")
    data.frombytes(np.ascontiguousarray(pixels).tobytes())
    return Image(
        header=header,
        height=h,
        width=w,
        encoding=encoding,
        is_bigendian=0,
        step=w * _CHANNELS,
        data=data,
    )


def image_rgb(msg: Image) -> np.ndarray:
    """An rgb8 or bgr8 Image as an (H, W, 3) RGB array."""
    if msg.encoding not in {"rgb8", "bgr8"}:
        raise ValueError(f"unsupported encoding {msg.encoding!r}")
    rows = np.frombuffer(msg.data, dtype=np.uint8).reshape(msg.height, msg.step)
    pixels = rows[:, : msg.width * _CHANNELS].reshape(msg.height, msg.width, _CHANNELS)
    return pixels[..., ::-1] if msg.encoding == "bgr8" else pixels


def detection_msg(det: Detection) -> Detection2D:
    msg = Detection2D()
    msg.bbox.center.position.x = (det.x1 + det.x2) / 2.0
    msg.bbox.center.position.y = (det.y1 + det.y2) / 2.0
    msg.bbox.size_x = det.x2 - det.x1
    msg.bbox.size_y = det.y2 - det.y1
    hyp = ObjectHypothesisWithPose()
    hyp.hypothesis.class_id = det.class_name
    hyp.hypothesis.score = float(det.score)
    msg.results.append(hyp)
    return msg


def detections_msg(dets: list[Detection], header: Header) -> Detection2DArray:
    msg = Detection2DArray(header=header)
    for d in dets:
        one = detection_msg(d)
        one.header = header
        msg.detections.append(one)
    return msg


def detections_from(msg: Detection2DArray, img_w: int, img_h: int) -> list[Detection]:
    """Back to certain_road's `Detection`. The array carries no image size, so the caller
    supplies the camera's; the box fields round-trip exactly."""
    out = []
    for d in msg.detections:
        best = max(d.results, key=lambda r: r.hypothesis.score)
        cx, cy = d.bbox.center.position.x, d.bbox.center.position.y
        hw, hh = d.bbox.size_x / 2.0, d.bbox.size_y / 2.0
        out.append(
            Detection(
                class_name=best.hypothesis.class_id,
                score=best.hypothesis.score,
                x1=cx - hw,
                y1=cy - hh,
                x2=cx + hw,
                y2=cy + hh,
                img_w=img_w,
                img_h=img_h,
            )
        )
    return out
