"""Detections from the camera frame: Model P and Model B, or the simulator's projection.

One output, `vision_msgs/Detection2DArray` on /perception/detections, from one of two
sources:

- **detector**: Model P for potholes and Model B for cracks (D082: never summed), on
  CUDA when torch sees the GPU and on the CPU otherwise, which is logged.
- **projection**: the boxes `certain_road.sim.project` computed for this exact frame,
  paired with it by timestamp. Used when torch, ultralytics or either weights file is
  missing. The run then says PROJECTION-ONLY in the log, on /perception/source and on
  every annotated frame, so a recording can never pass simulated ground truth off as
  model output.

`auto` tries the detector and falls back. Either way the frame is paired with its ground
truth, which the annotated image draws in thin white beside the detections, under the
corridor the planner judges and the planner's latest drive state.
"""

from __future__ import annotations

import time

import cv2
import numpy as np
import rclpy
import yaml
from message_filters import Subscriber, TimeSynchronizer
from rclpy.executors import ExternalShutdownException
from rclpy.node import Node
from sensor_msgs.msg import Image
from std_msgs.msg import String
from vision_msgs.msg import Detection2DArray

from certain_road.artifacts.schema import Detection
from certain_road.driving.corridor import CORRIDOR_CONFIG_PATH, corridor_polygon, load_corridor
from certain_road.sim.model import load_robot
from certain_road_ros.common import (
    LATCHED,
    LATEST,
    demo_config,
    detections_from,
    detections_msg,
    image_msg,
    image_rgb,
    repo_path,
)

SOURCES = ("auto", "detector", "projection")


class Detectors:
    """Model P and Model B on one frame, kept to the classes D082 assigns each."""

    def __init__(self, cfg: dict, img_w: int, img_h: int) -> None:
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
        self.img_w, self.img_h = img_w, img_h
        self.models = {m: YOLO(str(w)) for m, w in weights.items()}
        for m, model in self.models.items():
            absent = set(self.classes_from[m]) - set(model.names.values())
            if absent:
                raise ValueError(f"Model {m} has no class {sorted(absent)}: {model.names}")
        self(np.zeros((img_h, img_w, 3), dtype=np.uint8))  # warm-up: first call is slow

    def __call__(self, bgr: np.ndarray) -> list[Detection]:
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
                    out.append(Detection(name, float(s), *xyxy, self.img_w, self.img_h))
        return out


class PerceptionNode(Node):
    def __init__(self) -> None:
        super().__init__("perception_node")
        cfg = demo_config()
        self.cfg, self.topics = cfg["perception"], cfg["topics"]
        self.camera = load_robot(repo_path("configs", "sim", "robot.yaml")).camera
        poly = corridor_polygon(
            load_corridor(CORRIDOR_CONFIG_PATH), self.camera.img_w, self.camera.img_h
        )
        self.corridor_px = np.rint(poly).astype(np.int32)
        self.drive_state = "-"

        source = self.declare_parameter("source", "").value or self.cfg["source"]
        if source not in SOURCES:
            raise ValueError(f"source must be one of {SOURCES}, got {source!r}")
        self.detectors, self.label, detail = self._choose(source)

        t = self.topics
        self.pub_dets = self.create_publisher(Detection2DArray, t["detections"], LATEST)
        self.pub_annotated = self.create_publisher(Image, t["annotated"], LATEST)
        self.pub_source = self.create_publisher(String, t["source"], LATCHED)
        self.pub_source.publish(String(data=f"{self.label}: {detail}"))
        self.create_subscription(String, t["drive_state"], self._on_state, LATEST)
        self.sync = TimeSynchronizer(
            [
                Subscriber(self, Image, t["image"], qos_profile=LATEST),
                Subscriber(self, Detection2DArray, t["ground_truth"], qos_profile=LATEST),
            ],
            self.cfg["sync_queue"],
        )
        self.sync.registerCallback(self._on_frame)

    def _choose(self, source: str) -> tuple[Detectors | None, str, str]:
        """(detectors or None, banner label, why). The label is short enough for the frame."""
        log = self.get_logger()
        projection = "PROJECTION-ONLY: boxes are simulated ground truth"
        if source == "projection":
            log.warning(f"{projection} (source=projection was asked for)")
            return None, projection, "source=projection was asked for"
        try:
            detectors = Detectors(self.cfg, self.camera.img_w, self.camera.img_h)
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

    def _on_state(self, msg: String) -> None:
        self.drive_state = msg.data

    def _on_frame(self, image: Image, truth_msg: Detection2DArray) -> None:
        rgb = image_rgb(image)
        truth = detections_from(truth_msg, self.camera.img_w, self.camera.img_h)
        bgr = np.ascontiguousarray(rgb[..., ::-1])
        t0 = time.perf_counter()
        dets = self.detectors(bgr) if self.detectors else truth
        ms = (time.perf_counter() - t0) * 1e3
        self.pub_dets.publish(detections_msg(dets, image.header))
        self.pub_annotated.publish(
            image_msg(self._annotate(bgr, dets, truth, ms), image.header, "bgr8")
        )

    # ---- the annotated frame ---------------------------------------------------------

    def _annotate(
        self, bgr: np.ndarray, dets: list[Detection], truth: list[Detection], ms: float
    ) -> np.ndarray:
        o = self.cfg["overlay"]
        col = {k: tuple(int(c) for c in v) for k, v in o["colours_bgr"].items()}
        img = bgr.copy()
        shade = img.copy()
        cv2.fillPoly(shade, [self.corridor_px], col["corridor"])
        img = cv2.addWeighted(shade, o["corridor_alpha"], img, 1 - o["corridor_alpha"], 0)
        cv2.polylines(img, [self.corridor_px], True, col["corridor"], 1, cv2.LINE_AA)

        font, scale = cv2.FONT_HERSHEY_SIMPLEX, o["font_scale"]
        if self.detectors:
            for d in truth:
                p1, p2 = (int(d.x1), int(d.y1)), (int(d.x2), int(d.y2))
                cv2.rectangle(img, p1, p2, col["truth"], o["truth_px"], cv2.LINE_AA)
        for d in dets:
            c = col.get(d.class_name, col["text"])
            p1, p2 = (int(d.x1), int(d.y1)), (int(d.x2), int(d.y2))
            cv2.rectangle(img, p1, p2, c, o["box_px"], cv2.LINE_AA)
            tag = d.class_name if not self.detectors else f"{d.class_name} {d.score:.2f}"
            cv2.putText(img, tag, (p1[0], max(p1[1] - 4, 12)), font, scale, c, 1, cv2.LINE_AA)

        h, w = img.shape[:2]
        bh = o["banner_px"]
        banner = col["warn"] if not self.detectors else col["text"]
        cv2.rectangle(img, (0, 0), (w, bh), col["banner"], -1)
        cv2.putText(img, self.label, (6, bh - 8), font, scale, banner, 1, cv2.LINE_AA)
        cv2.rectangle(img, (0, h - bh), (w, h), col["banner"], -1)
        status = f"drive state: {self.drive_state.upper()}   boxes: {len(dets)}"
        if self.detectors:
            status += f"   {ms:.0f} ms"
        cv2.putText(img, status, (6, h - 8), font, scale, col["text"], 1, cv2.LINE_AA)
        return img


def main() -> None:
    rclpy.init()
    node = PerceptionNode()
    try:
        rclpy.spin(node)
    except (KeyboardInterrupt, ExternalShutdownException):
        pass
    finally:
        node.destroy_node()
        rclpy.try_shutdown()
