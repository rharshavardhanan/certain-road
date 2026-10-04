"""D075 — per-pothole confirmation on real road video, one model's pothole channel.

Runs ByteTrack over every frame, drops boxes whose bottom edge sits above the
horizon, and confirms a track once the same ID is present in 3 of the last 5
frames. The number it reports is **unique confirmed tracks, not potholes**: an ID
switch splits one pothole into two tracks and a merge folds two into one, and on
video with no ground truth neither error can be measured.

    uv run python scripts/eval_video.py data/video/<id>.mp4 --horizon 0.66 --model P

Writes `runs/video/<stem>/<model>/annotated.mp4` (large, derived from third-party
footage, gitignored) and `results/video/<stem>/<model>/summary.json`. Provenance is read from the
yt-dlp sidecar `<stem>.info.json` when it exists.
"""

import argparse
import hashlib
import json
import subprocess
import sys
import time
from pathlib import Path

import cv2
import numpy as np
import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from certain_road.core.paths import repo_root  # noqa: E402
from certain_road.driving.confirm import Confirmer  # noqa: E402

ROOT = repo_root()
CFG = yaml.safe_load((ROOT / "configs" / "project.yaml").read_text())
VCFG = yaml.safe_load((ROOT / "configs" / "eval" / "video.yaml").read_text())
WARMUP = yaml.safe_load((ROOT / "configs" / "eval" / "thresholds.yaml").read_text())[
    "latency_warmup"
]

# BGR drawing colours
RAW, GATED, CONFIRMED, HORIZON = (0, 215, 255), (150, 150, 150), (0, 200, 0), (255, 200, 0)
FONT = cv2.FONT_HERSHEY_SIMPLEX

CAVEATS = [
    "No ground truth. Nothing here is precision, recall or a miss rate; the count is unscored.",
    "Tracks, not potholes (D075). ID switches bias the count up (a pothole re-acquired under a "
    "new ID counts twice); merges bias it down (two potholes held by one ID count once). Without "
    "ground truth neither bias is measured. At conf 0.25 ByteTrack's low-score recovery stage "
    "receives no boxes, which favours ID switches.",
    "Unknown camera geometry: no intrinsics, mounting height or pitch, so no distances, sizes or "
    "ground positions. The horizon is a hand-set fraction of frame height (settings.horizon_frac), "
    "not a calibrated line.",
    "Latency is this Mac (Apple Silicon, MPS), not the Jetson target, and covers model.track() "
    "only: letterbox, inference, NMS and the ByteTrack update. Decode, drawing and encoding are "
    "excluded from it and included in end_to_end_fps.",
]

CONTAMINATION = {
    "B": "Training contamination, for Model B specifically: B is Model A (RDD2022, non-India) "
    "fine-tuned on RDD2022 india_train plus non-India replay. RDD2022 is not YouTube-derived, "
    "but this video has not been checked against its images. BharatPotHole (Indian dashcam "
    "footage) trained Model P, not B; its 162 source IDs are its authors' dashcam timestamps, "
    "not YouTube IDs, so this video is unlikely to be in it either.",
    "P": "Training contamination, for Model P specifically: P is Model B fine-tuned, pothole-only, "
    "on india_train plus BharatPotHole train (D074). BharatPotHole is Indian dashcam footage, "
    "the closest domain to this video any model here has seen. Its 162 source IDs are its "
    "authors' dashcam timestamps, not YouTube IDs, so this video is unlikely to be in it; that "
    "is inferred from filenames, not checked frame by frame.",
}


def confirm_step(
    confirmers: dict[int, Confirmer],
    tracks: list[tuple[int, float]],
    horizon_y: float,
    required: int,
    window: int,
) -> set[int]:
    """One frame of D075: gate on the horizon, then N-of-M per track ID.

    `tracks` is this frame's `(track_id, y2)` pairs; `confirmers` carries state
    between frames. Returns the IDs confirmed as of this frame.
    """
    present = {tid for tid, y2 in tracks if y2 >= horizon_y}
    for tid in present - confirmers.keys():
        confirmers[tid] = Confirmer(required, window)
    # ponytail: every track ever seen is updated every frame; prune stale IDs
    # if a long drive makes this slow.
    return {tid for tid, c in confirmers.items() if c.update(tid in present)}


def main() -> None:
    ap = argparse.ArgumentParser(description="D075 per-track pothole confirmation on a video")
    ap.add_argument("video", type=Path)
    ap.add_argument(
        "--horizon",
        type=float,
        default=VCFG["horizon_frac"],
        help="ROI gate: horizon as a fraction of frame height, set by eye per video",
    )
    ap.add_argument("--model", choices=sorted(VCFG["models"]), default="B")
    args = ap.parse_args()

    from ultralytics import YOLO

    model = YOLO(ROOT / VCFG["models"][args.model])
    pothole = list(model.names.values()).index("pothole")
    raw: list[np.ndarray] = []
    # Registered before the first track() call, so it runs ahead of the tracker's
    # own callback, which replaces result.boxes with tracked boxes only.
    model.add_callback(
        "on_predict_postprocess_end", lambda p: raw.append(p.results[0].boxes.data.cpu().numpy())
    )

    cap = cv2.VideoCapture(str(args.video))
    fps = cap.get(cv2.CAP_PROP_FPS)
    w, h = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)), int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    horizon_y = args.horizon * h

    mp4 = ROOT / "runs" / "video" / args.video.stem / args.model / "annotated.mp4"
    out = ROOT / "results" / "video" / args.video.stem / args.model / "summary.json"
    mp4.parent.mkdir(parents=True, exist_ok=True)
    out.parent.mkdir(parents=True, exist_ok=True)
    ff = subprocess.Popen(
        [
            "ffmpeg",
            "-v",
            "error",
            "-y",
            "-f",
            "rawvideo",
            "-pix_fmt",
            "bgr24",
            "-s",
            f"{w}x{h}",
            "-r",
            str(fps),
            "-i",
            "-",
            "-c:v",
            "libx264",
            "-pix_fmt",
            "yuv420p",
            "-crf",
            "23",
            "-movflags",
            "+faststart",
            str(mp4),
        ],
        stdin=subprocess.PIPE,
    )

    confirmers: dict[int, Confirmer] = {}
    ever: set[int] = set()
    tracks: dict[int, dict] = {}
    latency_ms: list[float] = []
    n_raw = n_gated = n = 0
    t_start = time.perf_counter()
    while True:
        ok, frame = cap.read()
        if not ok:
            break
        t0 = time.perf_counter()
        res = model.track(
            frame,
            persist=True,
            conf=VCFG["conf"],
            classes=[pothole],
            tracker=VCFG["tracker"],
            device=VCFG["device"],
            imgsz=CFG["eval"]["imgsz"],
            verbose=False,
        )[0]
        latency_ms.append((time.perf_counter() - t0) * 1000)
        dets = raw.pop()

        # When ByteTrack returns no tracks, ultralytics leaves the raw boxes in
        # result.boxes with id=None; those are detections, not tracks.
        tracked = res.boxes.is_track
        ids = res.boxes.id.int().tolist() if tracked else []
        boxes = res.boxes.xyxy.cpu().numpy() if tracked else np.empty((0, 4))
        confirmed = confirm_step(
            confirmers,
            [(t, b[3]) for t, b in zip(ids, boxes, strict=True)],
            horizon_y,
            **VCFG["confirm"],
        )
        for tid, b in zip(ids, boxes, strict=True):
            if b[3] >= horizon_y:
                tr = tracks.setdefault(tid, {"frames_detected": 0, "first_frame": n})
                tr["frames_detected"] += 1
                tr["last_frame"] = n
        for tid in confirmed - ever:
            tracks[tid]["confirmed_at"] = n
        ever |= confirmed

        for x1, y1, x2, y2, *_ in dets:
            gated = bool(y2 < horizon_y)
            n_raw += 1
            n_gated += gated
            cv2.rectangle(frame, (int(x1), int(y1)), (int(x2), int(y2)), GATED if gated else RAW, 1)
        for tid, (x1, y1, x2, y2) in zip(ids, boxes, strict=True):
            if tid in confirmed and y2 >= horizon_y:
                cv2.rectangle(frame, (int(x1), int(y1)), (int(x2), int(y2)), CONFIRMED, 3)
                cv2.putText(
                    frame, f"#{tid}", (int(x1), max(int(y1) - 6, 12)), FONT, 0.7, CONFIRMED, 2
                )
        cv2.line(frame, (0, int(horizon_y)), (w, int(horizon_y)), HORIZON, 1)
        cv2.rectangle(frame, (0, 0), (560, 62), (0, 0, 0), -1)
        cv2.putText(
            frame, f"unique confirmed tracks: {len(ever)}", (10, 30), FONT, 0.9, CONFIRMED, 2
        )
        cv2.putText(
            frame,
            f"tracks, not potholes (D075) | Model {args.model} conf {VCFG['conf']} | frame {n}",
            (10, 52),
            FONT,
            0.5,
            (255, 255, 255),
            1,
        )
        ff.stdin.write(frame.tobytes())
        n += 1

    wall = time.perf_counter() - t_start
    cap.release()
    ff.stdin.close()
    if ff.wait():
        sys.exit(f"ffmpeg failed with exit code {ff.returncode}")

    info_path = args.video.with_suffix(".info.json")
    info = json.loads(info_path.read_text()) if info_path.exists() else {}
    keys = (
        "webpage_url",
        "id",
        "title",
        "channel",
        "channel_url",
        "license",
        "upload_date",
        "duration",
        "section_start",
        "section_end",
    )
    with args.video.open("rb") as f:
        sha = hashlib.file_digest(f, "sha256").hexdigest()
    steady = latency_ms[WARMUP:]

    summary = {
        "video": {
            "path": str(args.video),
            "sha256": sha,
            "frames": n,
            "fps": fps,
            "width": w,
            "height": h,
            "duration_s": n / fps,
            "source": {k: info.get(k) for k in keys} if info else None,
        },
        "model": {
            "name": f"Model {args.model}",
            "weights": VCFG["models"][args.model],
            "class": "pothole",
            "class_id": pothole,
        },
        "settings": {
            "conf": VCFG["conf"],
            "tracker": VCFG["tracker"],
            "persist": True,
            "imgsz": CFG["eval"]["imgsz"],
            "device": VCFG["device"],
            "confirm": VCFG["confirm"],
            "horizon_frac": args.horizon,
            "horizon_y_px": horizon_y,
        },
        "result": {
            "unique_confirmed_tracks": len(ever),
            "count_is": "tracks, not potholes (D075)",
            "tracks_seen_below_horizon": len(tracks),
            "raw_detections": n_raw,
            "raw_detections_gated_above_horizon": n_gated,
            "confirmed_tracks": {str(t): tracks[t] for t in sorted(ever)},
        },
        "performance": {
            "video_fps": fps,
            "processing_fps": n / (sum(latency_ms) / 1000),
            "end_to_end_fps": n / wall,
            "latency_ms": {
                "p50": float(np.percentile(steady, 50)),
                "p95": float(np.percentile(steady, 95)),
                "n": len(steady),
                "warmup_excluded": WARMUP,
            },
        },
        "annotated_mp4": str(mp4.relative_to(ROOT)),
        "caveats": [*CAVEATS, CONTAMINATION[args.model]],
    }
    out.write_text(json.dumps(summary, indent=2) + "\n")
    print(json.dumps({k: summary[k] for k in ("result", "performance")}, indent=2)[:1500])
    print(f"wrote {out.relative_to(ROOT)} and {mp4.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
