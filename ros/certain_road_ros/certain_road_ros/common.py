"""What the three nodes share: the demo config, latched QoS and message conversions.

Conversions only. No node logic lives here, so each node file reads as its own
composition root.
"""

from __future__ import annotations

import array
import math
from functools import cache
from pathlib import Path

import numpy as np
import yaml
from geometry_msgs.msg import Quaternion
from rclpy.qos import DurabilityPolicy, QoSProfile, ReliabilityPolicy
from sensor_msgs.msg import Image
from std_msgs.msg import Header
from vision_msgs.msg import Detection2D, Detection2DArray, ObjectHypothesisWithPose

from certain_road.artifacts.schema import Detection
from certain_road.core.paths import repo_root

# Late joiners (RViz, a restarted planner) get the last value: scenario and source.
LATCHED = QoSProfile(
    depth=1,
    durability=DurabilityPolicy.TRANSIENT_LOCAL,
    reliability=ReliabilityPolicy.RELIABLE,
)
# Keep only the newest frame: a slow consumer skips frames rather than falling behind.
LATEST = QoSProfile(depth=1, reliability=ReliabilityPolicy.RELIABLE)

_CHANNELS = 3


def repo_path(*parts: str) -> Path:
    return repo_root().joinpath(*parts)


@cache
def demo_config() -> dict:
    return yaml.safe_load(repo_path("configs", "ros", "demo.yaml").read_text())


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
