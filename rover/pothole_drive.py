"""Drive the rover along the track, avoiding potholes it sees through the C920. Run over SSH.

    python rover/pothole_drive.py                 # DRY: everything runs, motors stay off
    python rover/pothole_drive.py --arm           # drives (3 s countdown first)
    python rover/pothole_drive.py --arm --heading-hold --can vcan0 --record run.mp4

Per frame, the same chain as every simulation in this repo: Model P (potholes) and Model B
(cracks), D082; then `build_perception` (corridor, escape zones, the 3-of-5 Confirmer),
`next_state` and `command_for`, unchanged. The Command becomes two motor duties
(rover/drivemap.py) for the L298N. Only potholes steer; cracks are drawn and logged.

Watch it from the Mac: http://host123.local:8080 shows the annotated camera, the drive state
and the duties. Every decision is logged to runs/rover/<UTC stamp>/decisions.csv.

SAFETY: motors move only with --arm. They stop on Ctrl-C, on any error, when no fresh decision
arrives within safety.watchdog_s, and after safety.max_run_s. Keep a battery switch in reach.
"""

from __future__ import annotations

import argparse
import csv
import signal
import sys
import threading
import time
from datetime import UTC, datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import cv2
import numpy as np
import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from drivemap import clamp, command_duties, load_config  # noqa: E402
from hardware import DryMotors, Motors, MPU6050Heading, find_imu  # noqa: E402

from certain_road.artifacts.schema import Detection  # noqa: E402
from certain_road.core.device import available_device  # noqa: E402
from certain_road.core.paths import repo_root  # noqa: E402
from certain_road.driving.confirm import Confirmer  # noqa: E402
from certain_road.driving.controller import command_for  # noqa: E402
from certain_road.driving.corridor import (  # noqa: E402
    CORRIDOR_CONFIG_PATH,
    corridor_polygon,
    load_corridor,
)
from certain_road.driving.decision import DriveState, load_policy, next_state  # noqa: E402
from certain_road.driving.perceive import build_perception  # noqa: E402

ROOT = repo_root()
VIDEO = yaml.safe_load((ROOT / "configs/eval/video.yaml").read_text())
DRIVE = yaml.safe_load((ROOT / "configs/sim/mujoco.yaml").read_text())["drive"]
HAZARDS = set(
    yaml.safe_load((ROOT / "configs/ros/demo.yaml").read_text())["planner"]["hazard_classes"]
)
CLASSES, COLOURS = DRIVE["classes_from"], DRIVE["colours_bgr"]
STATE_BGR = {
    "normal": (80, 200, 80),
    "warning": (40, 200, 240),
    "avoid_left": (40, 140, 255),
    "avoid_right": (40, 140, 255),
    "stop": (60, 60, 230),
}


def wrap(a: float) -> float:
    return (a + 180.0) % 360.0 - 180.0


class Stream:
    """The latest annotated frame as an MJPEG stream on http://<jetson>:port."""

    def __init__(self, port: int, quality: int) -> None:
        self.jpeg, self.quality, self.cond = b"", quality, threading.Condition()
        stream = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *a) -> None:  # quiet: the terminal is for the drive
                pass

            def do_GET(self) -> None:
                if self.path != "/stream":
                    page = (
                        b"<html><body style='margin:0;background:#111'><img src='/stream' "
                        b"style='width:100%'></body></html>"
                    )
                    self.send_response(200)
                    self.send_header("Content-Type", "text/html")
                    self.end_headers()
                    self.wfile.write(page)
                    return
                self.send_response(200)
                self.send_header("Content-Type", "multipart/x-mixed-replace; boundary=frame")
                self.end_headers()
                try:
                    while True:
                        with stream.cond:
                            stream.cond.wait(timeout=2.0)
                            jpeg = stream.jpeg
                        self.wfile.write(
                            b"--frame\r\nContent-Type: image/jpeg\r\n\r\n" + jpeg + b"\r\n"
                        )
                except (BrokenPipeError, ConnectionResetError):
                    return

        self.server = ThreadingHTTPServer(("0.0.0.0", port), Handler)
        threading.Thread(target=self.server.serve_forever, daemon=True).start()

    def push(self, bgr: np.ndarray, width: int) -> None:
        h, w = bgr.shape[:2]
        small = cv2.resize(bgr, (width, int(h * width / w)))
        ok, buf = cv2.imencode(".jpg", small, [cv2.IMWRITE_JPEG_QUALITY, self.quality])
        if ok:
            with self.cond:
                self.jpeg = buf.tobytes()
                self.cond.notify_all()

    def close(self) -> None:
        self.server.shutdown()


def open_camera(cam: dict) -> cv2.VideoCapture:
    cap = cv2.VideoCapture(cam["device"], cv2.CAP_V4L2)
    cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*"MJPG"))
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, cam["size"][0])
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, cam["size"][1])
    if not cam["autofocus"]:
        cap.set(cv2.CAP_PROP_AUTOFOCUS, 0)
        cap.set(cv2.CAP_PROP_FOCUS, cam["focus"])
    if not cap.isOpened():
        sys.exit(f"cannot open the camera {cam['device']}")
    return cap


def detect(models: dict, frame: np.ndarray, dev: str) -> list[Detection]:
    h, w = frame.shape[:2]
    out = []
    for m, model in models.items():
        r = model.predict(frame, conf=VIDEO["conf"], device=dev, verbose=False)[0]
        for c, s, (x1, y1, x2, y2) in zip(
            r.boxes.cls.tolist(), r.boxes.conf.tolist(), r.boxes.xyxy.tolist(), strict=True
        ):
            name = r.names[int(c)]
            if name in CLASSES[m]:  # D082: potholes from P, cracks from B
                out.append(Detection(name, float(s), x1, y1, x2, y2, w, h))
    return out


def annotate(frame, dets, poly, state, duties, fps, armed, extra) -> np.ndarray:
    img = frame.copy()
    shade = img.copy()
    cv2.fillPoly(shade, [poly], (168, 95, 43))
    img = cv2.addWeighted(shade, 0.18, img, 0.82, 0)
    cv2.polylines(img, [poly], True, (168, 95, 43), 2)
    for d in dets:
        col = tuple(COLOURS[d.class_name])
        cv2.rectangle(img, (int(d.x1), int(d.y1)), (int(d.x2), int(d.y2)), col, 3)
        cv2.putText(
            img,
            f"{d.class_name} {d.score:.2f}",
            (int(d.x1), max(int(d.y1) - 6, 18)),
            0,
            0.7,
            col,
            2,
        )
    banner = "ARMED: MOTORS LIVE" if armed else "DRY: motors off (add --arm)"
    cv2.rectangle(img, (0, 0), (img.shape[1], 44), (20, 20, 20), -1)
    cv2.putText(img, banner, (10, 30), 0, 0.9, (60, 60, 230) if armed else (200, 200, 200), 2)
    cv2.putText(
        img,
        f"{state.upper()}",
        (img.shape[1] - 260, 32),
        0,
        1.0,
        STATE_BGR.get(state, (255, 255, 255)),
        3,
    )
    status = f"L {duties[0]:+4.0f}%  R {duties[1]:+4.0f}%   {fps:4.1f} fps   {extra}"
    cv2.putText(img, status, (10, img.shape[0] - 16), 0, 0.8, (255, 255, 255), 2)
    return img


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--arm", action="store_true", help="drive the motors (default: dry)")
    ap.add_argument("--heading-hold", action="store_true", help="MPU6050 heading hold")
    ap.add_argument("--can", metavar="IFACE", help="also send each Command as a CAN frame")
    ap.add_argument("--record", type=Path, help="also save the annotated view as mp4")
    ap.add_argument("--max-run-s", type=float, help="override safety.max_run_s")
    args = ap.parse_args()
    cfg = load_config()
    safety = cfg["safety"]
    max_run = args.max_run_s or safety["max_run_s"]

    corridor = load_corridor(CORRIDOR_CONFIG_PATH)
    policy = load_policy(ROOT / "configs/driving/decision.yaml")
    escape = float(yaml.safe_load(CORRIDOR_CONFIG_PATH.read_text())["escape_lanes"])
    confirmer, state = Confirmer(policy.required, policy.window), DriveState.NORMAL

    from ultralytics import YOLO

    dev = available_device(VIDEO["device"])
    models = {m: YOLO(ROOT / VIDEO["models"][m]) for m in CLASSES}
    cap = open_camera(cfg["camera"])
    ok, frame = cap.read()
    if not ok:
        sys.exit("no frame from the camera")
    detect(models, frame, dev)  # warm-up: the first inference is slow
    h, w = frame.shape[:2]
    poly = np.rint(corridor_polygon(corridor, w, h)).astype(np.int32)

    imu, target = None, 0.0
    if args.heading_hold:
        ic = cfg["imu"]
        bus = find_imu(ic["buses"], ic["addr"])
        if bus is None:
            sys.exit(f"no MPU6050 at 0x{ic['addr']:02x} on i2c buses {ic['buses']}: check wiring")
        imu = MPU6050Heading(bus, ic["addr"], ic["max_rate_dps"])
        print(
            f"IMU on i2c-{bus}: keep the rover still for {ic['bias_seconds']:.0f} s...", flush=True
        )
        imu.calibrate(ic["bias_seconds"])
        imu.start()
        time.sleep(0.2)
        target = imu.get()[0]

    can = None
    if args.can:
        from certain_road.canbus.transport import CanTransport, load_transport_config

        tc = load_transport_config(ROOT / "configs/canbus/transport.yaml")
        can = CanTransport(type(tc)("socketcan", args.can, tc.arbitration_id))

    motors = Motors(cfg) if args.arm else DryMotors()
    stream = Stream(cfg["stream"]["port"], cfg["stream"]["jpeg_quality"])
    out_dir = ROOT / "runs/rover" / datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    out_dir.mkdir(parents=True, exist_ok=True)
    logf = (out_dir / "decisions.csv").open("w", newline="")
    log = csv.writer(logf)
    log.writerow(
        [
            "t_s",
            "state",
            "action",
            "speed",
            "steer",
            "left",
            "right",
            "potholes",
            "cracks",
            "heading_deg",
        ]
    )
    writer = None
    last_decision = [time.time()]
    stopping = threading.Event()

    def watchdog() -> None:  # the decision loop stalled: stop rather than drive blind
        while not stopping.is_set():
            if time.time() - last_decision[0] > safety["watchdog_s"]:
                motors.stop()
            time.sleep(0.05)

    signal.signal(signal.SIGTERM, lambda *_: stopping.set())
    print(
        f"live view: http://host123.local:{cfg['stream']['port']}  (or the Jetson's IP)", flush=True
    )
    print(f"log: {out_dir / 'decisions.csv'}", flush=True)
    if args.arm:
        for k in range(int(safety["arm_countdown_s"]), 0, -1):
            print(f"ARMED: motors start in {k} s (Ctrl-C to abort)", flush=True)
            time.sleep(1)
    threading.Thread(target=watchdog, daemon=True).start()

    t0 = time.time()
    frames, counts = 0, {}
    try:
        while not stopping.is_set() and time.time() - t0 < max_run:
            ok, frame = cap.read()
            if not ok:
                print("camera stopped", flush=True)
                break
            dets = detect(models, frame, dev)
            hazards = [d for d in dets if d.class_name in HAZARDS]
            perception, _ = build_perception(hazards, corridor, confirmer, escape_lanes=escape)
            state = next_state(state, perception, policy)
            command = command_for(state, policy)
            hold, heading = 0.0, ""
            if imu is not None:
                hdg, age = imu.get()
                if age > 0.2:
                    raise RuntimeError(f"IMU data stale ({age:.2f} s)")
                if state in (DriveState.NORMAL, DriveState.WARNING):
                    ic = cfg["imu"]
                    hold = clamp(
                        ic["hold_kp"] * wrap(target - hdg), -ic["hold_max"], ic["hold_max"]
                    )
                heading = f"{hdg:+.1f}"
            left, right = command_duties(command, cfg, hold)
            motors.set(left, right)
            last_decision[0] = time.time()
            if can is not None:
                can.send(command)

            frames += 1
            counts[str(state)] = counts.get(str(state), 0) + 1
            fps = frames / (time.time() - t0)
            n_pot = sum(d.class_name == "pothole" for d in dets)
            log.writerow(
                [
                    f"{time.time() - t0:.3f}",
                    str(state),
                    command.action.name,
                    f"{command.speed:.2f}",
                    f"{command.steer:+.2f}",
                    f"{left:.0f}",
                    f"{right:.0f}",
                    n_pot,
                    len(dets) - n_pot,
                    heading,
                ]
            )
            extra = f"hdg {heading}" if heading else ""
            img = annotate(frame, dets, poly, str(state), (left, right), fps, args.arm, extra)
            stream.push(img, cfg["stream"]["width"])
            if args.record:
                if writer is None:
                    writer = cv2.VideoWriter(
                        str(args.record),
                        cv2.VideoWriter_fourcc(*"mp4v"),
                        10,
                        (img.shape[1], img.shape[0]),
                    )
                writer.write(img)
    except KeyboardInterrupt:
        print("\nstopped by Ctrl-C", flush=True)
    finally:
        stopping.set()
        motors.stop()
        motors.close()
        cap.release()
        if imu is not None:
            imu.close()
        if writer is not None:
            writer.release()
        logf.close()
        stream.close()
        took = time.time() - t0
        print(
            f"motors stopped. {frames} frames in {took:.0f} s ({frames / max(took, 1e-6):.1f}"
            f" fps); states {counts}; log {out_dir / 'decisions.csv'}"
        )


if __name__ == "__main__":
    main()
