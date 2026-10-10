"""Model P and Model B live on a USB webcam (the robot's Logitech C920): step 1 of the robot plan.

    .venv/bin/python scripts/webcam_live.py [--device /dev/video0] [--record out.mp4]

Potholes from Model P, cracks from Model B (D082), boxed in their class colours (configs/
sim/mujoco.yaml drive.colours_bgr), with the frame rate and running counts on screen. q or Esc
quits and prints how many frames had a pothole. No tracking or confirmation here: this checks
what the detectors see through this camera, at this height, on these prints (ros/WORKLOG §16).
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

import cv2
import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from certain_road.core.device import available_device  # noqa: E402
from certain_road.core.paths import repo_root  # noqa: E402

ROOT = repo_root()
VIDEO = yaml.safe_load((ROOT / "configs/eval/video.yaml").read_text())
DRIVE = yaml.safe_load((ROOT / "configs/sim/mujoco.yaml").read_text())["drive"]
CLASSES, COLOURS = DRIVE["classes_from"], DRIVE["colours_bgr"]
SIZE = (1280, 720)  # the C920's 720p mode; MJPG keeps it at 30 fps over USB 2


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--device", default="/dev/video0")
    ap.add_argument("--record", type=Path, help="also write the annotated view here")
    args = ap.parse_args()

    from ultralytics import YOLO

    dev = available_device(VIDEO["device"])
    models = {m: YOLO(ROOT / VIDEO["models"][m]) for m in CLASSES}
    cap = cv2.VideoCapture(args.device, cv2.CAP_V4L2)
    cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*"MJPG"))
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, SIZE[0])
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, SIZE[1])
    writer = None
    frames = with_pothole = 0
    t0 = time.perf_counter()
    while True:
        ok, frame = cap.read()
        if not ok:
            break
        counts = {}
        for m, model in models.items():
            r = model.predict(frame, conf=VIDEO["conf"], device=dev, verbose=False)[0]
            for c, s, (x1, y1, x2, y2) in zip(
                r.boxes.cls.tolist(), r.boxes.conf.tolist(), r.boxes.xyxy.tolist(), strict=True
            ):
                name = r.names[int(c)]
                if name not in CLASSES[m]:
                    continue
                counts[name] = counts.get(name, 0) + 1
                col = tuple(COLOURS[name])
                cv2.rectangle(frame, (int(x1), int(y1)), (int(x2), int(y2)), col, 3)
                label = f"{m} {name} {s:.2f}"
                cv2.putText(frame, label, (int(x1), max(int(y1) - 6, 16)), 0, 0.7, col, 2)
        frames += 1
        with_pothole += counts.get("pothole", 0) > 0
        fps = frames / (time.perf_counter() - t0)
        status = f"{fps:4.1f} fps on {dev}   " + "  ".join(f"{k}: {v}" for k, v in counts.items())
        cv2.putText(frame, status, (10, 30), 0, 0.8, (255, 255, 255), 2)
        if args.record:
            if writer is None:
                fourcc = cv2.VideoWriter_fourcc(*"mp4v")
                writer = cv2.VideoWriter(str(args.record), fourcc, 15, SIZE)
            writer.write(frame)
        cv2.imshow("certain-road: webcam, Model P + B", frame)
        if cv2.waitKey(1) & 0xFF in (27, ord("q")):
            break
    cap.release()
    if writer is not None:
        writer.release()
    cv2.destroyAllWindows()
    share = with_pothole / max(frames, 1)
    print(f"{frames} frames, {with_pothole} with a pothole box ({share:.0%})")


if __name__ == "__main__":
    main()
