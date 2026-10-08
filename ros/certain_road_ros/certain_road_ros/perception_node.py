"""Detections from any camera frame: Model P and Model B, or the simulator's projection.

One output, `vision_msgs/Detection2DArray` on /perception/detections, from one of two
sources:

- **detector**: Model P for potholes and Model B for cracks (D082: never summed), on
  CUDA when torch sees the GPU and on the CPU otherwise, which is logged.
- **projection**: the boxes `certain_road.sim.project` computed for this exact frame,
  paired with it by timestamp. Used when torch, ultralytics or either weights file is
  missing. The run then says PROJECTION-ONLY in the log, on /perception/source and on
  every annotated frame, so a recording can never pass simulated ground truth off as
  model output.

`auto` tries the detector and falls back.

**Any camera.** Frames come from /camera/image_raw, whoever publishes it: `sim_node`,
`video_node` or a Gazebo camera. Every size is the frame's own (the 2D sim is 640x640, the
road video 1280x720). A frame waits for its /sim/ground_truth only while that topic has a
publisher (`ground_truth:=auto`; `on` and `off` force it), so without the simulator the
detector runs alone. A frame from `video_node` is also paired with its /video/frame_info,
which adds the ground-truth strip and the open-loop notice to the annotated frame.

The annotated frame draws the simulator's ground truth in thin white beside the
detections, under the corridor the planner judges (`vehicle:=` / `corridor:=`, as the
planner's), the planner's latest drive state and the latest CAN frame on the bus.
"""

from __future__ import annotations

import os
import signal
import sys
import time

import cv2
import numpy as np
import rclpy
import yaml
from diagnostic_msgs.msg import DiagnosticArray
from rclpy.executors import ExternalShutdownException
from rclpy.node import Node
from rclpy.qos import QoSProfile, ReliabilityPolicy
from rclpy.signals import SignalHandlerOptions
from sensor_msgs.msg import Image
from std_msgs.msg import String
from vision_msgs.msg import Detection2DArray

from certain_road.artifacts.schema import Detection
from certain_road.driving.corridor import corridor_polygon, load_corridor
from certain_road_ros.common import (
    LATCHED,
    LATEST,
    StampPairer,
    demo_config,
    detections_from,
    detections_msg,
    frame_info_from,
    image_msg,
    image_rgb,
    profile,
    repo_path,
    stamp_key,
)
from certain_road_ros.video import FrameInfo

SOURCES = ("auto", "detector", "projection")
PAIRING = ("auto", "on", "off")
_TRUTH, _INFO = "ground_truth", "frame_info"
_CHANNELS = 3


class Detectors:
    """Model P and Model B on one frame of any size, kept to the classes D082 assigns each."""

    def __init__(self, cfg: dict) -> None:
        video = yaml.safe_load(repo_path("configs", "eval", "video.yaml").read_text())
        self.classes_from = cfg["classes_from"]
        weights = {m: repo_path(video["models"][m]) for m in self.classes_from}
        missing = [str(w) for w in weights.values() if not w.exists()]
        if missing:
            raise FileNotFoundError(f"weights not found: {', '.join(missing)}")

        import torch  # imported here: projection-only must work without torch installed
        from ultralytics import YOLO

        self.cuda = torch.cuda.is_available()
        self.device = "cuda:0" if self.cuda else "cpu"
        self.conf, self.imgsz = cfg["conf"], cfg["imgsz"]
        self.models = {m: YOLO(str(w)) for m, w in weights.items()}
        for m, model in self.models.items():
            absent = set(self.classes_from[m]) - set(model.names.values())
            if absent:
                raise ValueError(f"Model {m} has no class {sorted(absent)}: {model.names}")
        # warm-up: the first call is slow
        self(np.zeros((self.imgsz, self.imgsz, _CHANNELS), dtype=np.uint8))

    def __call__(self, bgr: np.ndarray) -> list[Detection]:
        img_h, img_w = bgr.shape[:2]
        out = []
        for m, model in self.models.items():
            r = model.predict(
                bgr, conf=self.conf, imgsz=self.imgsz, device=self.device, verbose=False
            )[0]
            b = r.boxes
            for c, s, xyxy in zip(
                b.cls.int().tolist(), b.conf.tolist(), b.xyxy.tolist(), strict=True
            ):
                name = r.names[c]
                if name in self.classes_from[m]:
                    out.append(Detection(name, float(s), *xyxy, img_w, img_h))
        return out


class PerceptionNode(Node):
    def __init__(self) -> None:
        super().__init__("perception_node")
        cfg = demo_config()
        self.cfg, self.topics = cfg["perception"], cfg["topics"]
        # the corridor the planner judges with, drawn on the frame (corridor:=, as the planner's)
        _, _, corridor, corridor_path = profile(
            self.declare_parameter("vehicle", "").value,
            self.declare_parameter("corridor", "").value,
        )
        self.corridor = load_corridor(corridor_path)
        self._corridor_px: dict[tuple[int, int], np.ndarray] = {}
        live = yaml.safe_load(repo_path("configs", "eval", "video.yaml").read_text())["live"]
        self.gt_bgr = {
            True: tuple(int(c) for c in live["gt_rgb_in_view"]),
            False: tuple(int(c) for c in live["gt_rgb_clear"]),
        }
        self.drive_state = "-"
        self.can_frame = ""

        source = self.declare_parameter("source", "").value or self.cfg["source"]
        if source not in SOURCES:
            raise ValueError(f"source must be one of {SOURCES}, got {source!r}")
        pairing = self.declare_parameter("ground_truth", "").value or self.cfg["ground_truth"]
        if pairing not in PAIRING:
            raise ValueError(f"ground_truth must be one of {PAIRING}, got {pairing!r}")
        if source == "projection" and pairing == "off":
            raise ValueError("source=projection draws the simulator's ground truth: it needs it")
        self.pairing = pairing
        self.detectors, self.label, detail = self._choose(source)

        t = self.topics
        self.pub_dets = self.create_publisher(Detection2DArray, t["detections"], LATEST)
        self.pub_annotated = self.create_publisher(Image, t["annotated"], LATEST)
        self.pub_source = self.create_publisher(String, t["source"], LATCHED)
        self.pub_source.publish(String(data=f"{self.label}: {detail}"))
        self.create_subscription(String, t["drive_state"], self._on_state, LATEST)
        self.create_subscription(String, t["can_decoded"], self._on_can, LATEST)

        self.pairer = StampPairer([_TRUTH, _INFO], self.cfg["sync_queue"])
        info_qos = QoSProfile(
            depth=self.cfg["frame_info_queue"], reliability=ReliabilityPolicy.RELIABLE
        )
        self.create_subscription(Image, t["image"], self._on_image, LATEST)
        self.create_subscription(Detection2DArray, t["ground_truth"], self._on_truth, LATEST)
        self.create_subscription(DiagnosticArray, t["frame_info"], self._on_info, info_qos)
        when = {
            "auto": f"while {t['ground_truth']} has a publisher",
            "on": "always",
            "off": "never",
        }[pairing]
        self.get_logger().info(f"frames from {t['image']}; paired with ground truth {when}")

    def _choose(self, source: str) -> tuple[Detectors | None, str, str]:
        """(detectors or None, banner label, why). The label is short enough for the frame."""
        log = self.get_logger()
        projection = "PROJECTION-ONLY: boxes are simulated ground truth"
        if source == "projection":
            log.warning(f"{projection} (source=projection was asked for)")
            return None, projection, "source=projection was asked for"
        try:
            detectors = Detectors(self.cfg)
        except (ImportError, FileNotFoundError) as exc:
            if source == "detector":
                raise
            log.warning(f"{projection}. Detector unavailable: {exc}")
            return None, projection, f"detector unavailable: {exc}"
        if not detectors.cuda:
            log.warning("torch sees no CUDA device: the detectors run on the CPU and will be slow")
        label = f"DETECTOR: Model P (pothole) + Model B (cracks) on {detectors.device}"
        log.info(label)
        return detectors, label, "D082: potholes from P, cracks from B, never summed"

    # ---- pairing: a frame, its ground truth when the sim sends one, its video facts ----

    def _needs(self) -> set[str]:
        """The companions this frame waits for, by who is publishing right now."""
        t, needs = self.topics, set()
        if self.pairing == "on" or (
            self.pairing == "auto" and self.count_publishers(t["ground_truth"]) > 0
        ):
            needs.add(_TRUTH)
        if self.count_publishers(t["frame_info"]) > 0:
            needs.add(_INFO)
        return needs

    def _on_image(self, msg: Image) -> None:
        for image, companions in self.pairer.add_primary(
            stamp_key(msg.header.stamp), msg, self._needs()
        ):
            self._on_frame(image, companions)

    def _on_truth(self, msg: Detection2DArray) -> None:
        for image, companions in self.pairer.add_companion(
            _TRUTH, stamp_key(msg.header.stamp), msg
        ):
            self._on_frame(image, companions)

    def _on_info(self, msg: DiagnosticArray) -> None:
        for image, companions in self.pairer.add_companion(_INFO, stamp_key(msg.header.stamp), msg):
            self._on_frame(image, companions)

    def _on_state(self, msg: String) -> None:
        self.drive_state = msg.data

    def _on_can(self, msg: String) -> None:
        self.can_frame = msg.data.split(" ", 1)[0]  # the candump-style frame, e.g. 101#0159A701

    def _on_frame(self, image: Image, companions: dict) -> None:
        rgb = image_rgb(image)
        img_h, img_w = rgb.shape[:2]
        truth = detections_from(companions[_TRUTH], img_w, img_h) if _TRUTH in companions else None
        info = frame_info_from(companions[_INFO]) if _INFO in companions else None
        if self.detectors is None and truth is None:
            self.get_logger().error(
                "no detector and no simulator ground truth to project: nothing to publish. "
                "Run with the weights in place, or with sim_node.",
                once=True,
            )
            return
        bgr = np.ascontiguousarray(rgb[..., ::-1])
        t0 = time.perf_counter()
        dets = self.detectors(bgr) if self.detectors else truth
        ms = (time.perf_counter() - t0) * 1e3
        self.pub_dets.publish(detections_msg(dets, image.header))
        annotated = self._annotate(bgr, dets, truth or [], ms, info)
        self.pub_annotated.publish(image_msg(annotated, image.header, "bgr8"))

    # ---- the annotated frame ---------------------------------------------------------

    def _corridor(self, img_w: int, img_h: int) -> np.ndarray:
        key = (img_w, img_h)
        if key not in self._corridor_px:
            poly = corridor_polygon(self.corridor, img_w, img_h)
            self._corridor_px[key] = np.rint(poly).astype(np.int32)
        return self._corridor_px[key]

    def _annotate(
        self,
        bgr: np.ndarray,
        dets: list[Detection],
        truth: list[Detection],
        ms: float,
        info: FrameInfo | None,
    ) -> np.ndarray:
        o = self.cfg["overlay"]
        col = {k: tuple(int(c) for c in v) for k, v in o["colours_bgr"].items()}
        h, w = bgr.shape[:2]
        # 1x up to scale_ref_px wide (the sim frame), proportionally larger above it
        k = max(1.0, w / o["scale_ref_px"])
        font, scale, thick = cv2.FONT_HERSHEY_SIMPLEX, o["font_scale"] * k, max(1, round(k))
        bh, pad, base = round(o["banner_px"] * k), round(6 * k), round(8 * k)
        corridor = self._corridor(w, h)

        img = bgr.copy()
        shade = img.copy()
        cv2.fillPoly(shade, [corridor], col["corridor"])
        img = cv2.addWeighted(shade, o["corridor_alpha"], img, 1 - o["corridor_alpha"], 0)
        cv2.polylines(img, [corridor], True, col["corridor"], thick, cv2.LINE_AA)

        if self.detectors:
            for d in truth:
                p1, p2 = (int(d.x1), int(d.y1)), (int(d.x2), int(d.y2))
                cv2.rectangle(img, p1, p2, col["truth"], round(o["truth_px"] * k), cv2.LINE_AA)
        for d in dets:
            c = col.get(d.class_name, col["text"])
            p1, p2 = (int(d.x1), int(d.y1)), (int(d.x2), int(d.y2))
            cv2.rectangle(img, p1, p2, c, round(o["box_px"] * k), cv2.LINE_AA)
            tag = d.class_name if not self.detectors else f"{d.class_name} {d.score:.2f}"
            at = (p1[0], max(p1[1] - round(4 * k), round(12 * k)))
            cv2.putText(img, tag, at, font, scale, c, thick, cv2.LINE_AA)

        label_colour = col["warn"] if not self.detectors else col["text"]
        status = f"drive state: {self.drive_state.upper()}   boxes: {len(dets)}"
        if self.detectors:
            status += f"   {ms:.0f} ms"
        can_text = f"CAN {self.can_frame}" if self.can_frame else ""
        style = (font, scale, thick, bh, pad, base, col["text"])
        if info is None:  # the sim: banners over the frame, as D093 drew them
            cv2.rectangle(img, (0, 0), (w, bh), col["banner"], -1)
            _write(img, bh, self.label, label_colour, "", style)
            cv2.rectangle(img, (0, h - bh), (w, h), col["banner"], -1)
            _write(img, h, status, col["text"], can_text, style)
            return img

        # A video: every banner goes outside the frame, so no road is covered. Above, the
        # ground truth at this video time; below, the decision and the open-loop notice.
        when = f"t {info.video_time_s:.2f} s   {info.pacing}"
        credit = f"video: {info.credit}   frame {info.frame}" if info.credit else ""
        bands = [
            (self.gt_bgr[bool(info.gt_in_view)], info.strip, col["text"], when),
            (col["banner"], self.label, label_colour, ""),
            None,  # the frame
            (col["banner"], status, col["text"], can_text),
            (col["banner"], info.notice, col["warn"], ""),
            (col["banner"], credit, col["text"], ""),
        ]
        return np.vstack([img if b is None else _band(w, *b, style) for b in bands])


def _write(img: np.ndarray, bottom: int, left: str, colour, right: str, style: tuple) -> None:
    """One line of banner text ending `bottom` px down; `right` right-aligned where it fits."""
    font, scale, thick, _, pad, base, right_colour = style
    cv2.putText(img, left, (pad, bottom - base), font, scale, colour, thick, cv2.LINE_AA)
    if not right:
        return
    used = cv2.getTextSize(left, font, scale, thick)[0][0] + 2 * pad
    tw = cv2.getTextSize(right, font, scale, thick)[0][0]
    x = img.shape[1] - tw - pad
    if x > used:
        cv2.putText(img, right, (x, bottom - base), font, scale, right_colour, thick, cv2.LINE_AA)


def _band(w: int, bg, left: str, colour, right: str, style: tuple) -> np.ndarray:
    bh = style[3]
    band = np.empty((bh, w, _CHANNELS), np.uint8)
    band[:] = bg
    _write(band, bh, left, colour, right, style)
    return band


def main() -> None:
    """Stops between frames, never inside one, and then exits at once.

    Left to rclpy's handlers, a SIGINT that lands inside a CUDA inference call (under
    realtime pacing perception is always mid-frame) left the process hung at exit, deaf to
    SIGTERM; the signal now only sets a flag. After the node is down, the interpreter's own
    teardown of torch and CUDA sometimes outlasted launch's 5 s SIGINT grace on the Jetson,
    so it is skipped with os._exit: this node writes no files, so nothing is lost."""
    rclpy.init(signal_handler_options=SignalHandlerOptions.NO)
    node = PerceptionNode()
    stop: list[int] = []
    for sig in (signal.SIGINT, signal.SIGTERM):
        signal.signal(sig, lambda signum, _frame: stop.append(signum))
    try:
        while rclpy.ok() and not stop:
            rclpy.spin_once(node, timeout_sec=node.cfg["stop_poll_s"])
    except ExternalShutdownException:
        pass
    finally:
        node.destroy_node()
        rclpy.try_shutdown()
    sys.stdout.flush()
    sys.stderr.flush()
    os._exit(0)
