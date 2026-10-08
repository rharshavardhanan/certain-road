"""Model P and Model B live on a real road video, against its hand-counted ground truth (D094).

    uv run python scripts/live_video.py data/video/2DV-cYmIvT4.mp4 [--record out.mp4] [--headless]

Every frame goes through both models with ByteTrack, as `eval_video.py` runs one: potholes
from P only and cracks from B only (D082), each confirmed by D075's 3-of-5 rule behind the
horizon gate (`confirm_step`, imported, not copied). Boxes take their class colour and turn
green once confirmed. The ground-truth strip lights while one of the hand-counted potholes
is in view, and Model P's confirmed tracks are scored live with `score_video_gt.score_tracks`,
the rule the offline numbers use, over the ground truth's window.

**Every frame is processed, none skipped.** D088: confirmation collapses when frames are
dropped. If the GPU cannot keep up with 30 fps the window plays slower than real time and
says so; `--record` writes at the video's own rate, so the recording plays in real time.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

import cv2
import numpy as np
import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from eval_video import VCFG, confirm_step  # noqa: E402  D075, one definition
from score_video_gt import read_gt, score_tracks  # noqa: E402  the offline scoring rule

from certain_road.core.paths import repo_root  # noqa: E402

ROOT = repo_root()
LIVE = VCFG["live"]
DRIVE = yaml.safe_load((ROOT / "configs" / "sim" / "mujoco.yaml").read_text())["drive"]
CLASSES = DRIVE["classes_from"]  # D082
COLOURS = {k: tuple(v) for k, v in DRIVE["colours_bgr"].items()}
FONT = cv2.FONT_HERSHEY_SIMPLEX
NAME = "certain-road: Model P + Model B on a real road"


class Model:
    """One detector, its ByteTrack state, its D075 confirmers and its track book."""

    def __init__(self, tag: str, horizon_y: float) -> None:
        from ultralytics import YOLO

        self.tag, self.horizon_y = tag, horizon_y
        self.yolo = YOLO(ROOT / VCFG["models"][tag])
        names = self.yolo.names
        self.classes = [i for i, n in names.items() if n in CLASSES[tag]]
        self.names = names
        self.confirmers: dict = {}
        self.tracks: dict[int, dict] = {}
        self.ever: set[int] = set()
        self.ms = 0.0

    def step(self, bgr: np.ndarray, n: int) -> list[tuple]:
        t0 = time.perf_counter()
        res = self.yolo.track(
            bgr,
            persist=True,
            tracker=VCFG["tracker"],
            conf=VCFG["conf"],
            device=VCFG["device"],
            classes=self.classes,
            verbose=False,
        )[0]
        self.ms = (time.perf_counter() - t0) * 1e3
        b = res.boxes
        if not b.is_track:
            return []
        ids, xyxy = b.id.int().tolist(), b.xyxy.cpu().numpy()
        cls, conf = b.cls.int().tolist(), b.conf.tolist()
        confirmed = confirm_step(
            self.confirmers,
            [(t, box[3]) for t, box in zip(ids, xyxy, strict=True)],
            self.horizon_y,
            **VCFG["confirm"],
        )
        for tid, box in zip(ids, xyxy, strict=True):  # the book eval_video.py keeps
            if box[3] >= self.horizon_y:
                tr = self.tracks.setdefault(tid, {"frames_detected": 0, "first_frame": n})
                tr["frames_detected"] += 1
                tr["last_frame"] = n
        for tid in confirmed - self.ever:
            self.tracks[tid]["confirmed_at"] = n
        self.ever |= confirmed
        return [
            (self.names[c], s, box, tid, tid in confirmed)
            for c, s, box, tid in zip(cls, conf, xyxy, ids, strict=True)
        ]

    def confirmed_tracks(self) -> dict[str, dict]:
        return {str(t): v for t, v in self.tracks.items() if "confirmed_at" in v}


def text(img, s, org, scale, colour, thick=1) -> None:
    cv2.putText(img, s, org, FONT, scale, (0, 0, 0), thick + 2, cv2.LINE_AA)
    cv2.putText(img, s, org, FONT, scale, colour, thick, cv2.LINE_AA)


def draw(frame, dets, t_s, gt, k_in_view, stats, horizon_y) -> np.ndarray:
    sc = LIVE["font_scale"]
    h, w = frame.shape[:2]
    bh, ph = LIVE["banner_px"], LIVE["panel_px"]
    out = np.zeros((h + bh * 2 + ph, w, 3), np.uint8)
    out[bh * 2 : bh * 2 + h] = frame
    y0 = bh * 2
    for x in range(0, w, 24):  # the horizon gate, dashed
        cv2.line(out, (x, y0 + int(horizon_y)), (x + 12, y0 + int(horizon_y)), (255, 200, 0), 1)
    for name, score, (x1, y1, x2, y2), tid, conf in dets:
        colour = COLOURS["confirmed"] if conf else COLOURS[name]
        p1, p2 = (int(x1), y0 + int(y1)), (int(x2), y0 + int(y2))
        cv2.rectangle(out, p1, p2, colour, 3 if conf else 1, cv2.LINE_AA)
        model = "P" if name == "pothole" else "B"
        text(
            out,
            f"{model} {name} {score:.2f} #{tid}",
            (p1[0], max(p1[1] - 5, y0 + 14)),
            sc * 0.8,
            colour,
        )

    text(out, f"REAL ROAD  {LIVE['credit']}", (10, bh - 10), sc, (240, 240, 240))
    rate = (
        f"t {t_s:6.1f} s   {stats['fps']:4.1f} fps on {VCFG['device']}  "
        f"P {stats['P_ms']:.0f} ms  B {stats['B_ms']:.0f} ms"
    )
    text(out, rate, (w - 560, bh - 10), sc, (200, 200, 200))
    strip = LIVE["gt_rgb_in_view"] if k_in_view else LIVE["gt_rgb_clear"]
    cv2.rectangle(out, (0, bh), (w, bh * 2), tuple(strip), -1)
    gt_s = (
        f"GROUND TRUTH: pothole #{k_in_view} of {len(gt)} in view"
        if k_in_view
        else "ground truth: no counted pothole in view"
    )
    text(out, gt_s, (10, bh * 2 - 10), sc, (255, 255, 255))

    py = y0 + h
    text(
        out,
        f"Model P (potholes): {stats['P_confirmed']} confirmed tracks   counted potholes passed "
        f"{stats['passed']}, caught {stats['caught']}",
        (10, py + 26),
        sc,
        COLOURS["pothole"],
    )
    text(
        out,
        f"Model B (cracks): {stats['B_confirmed']} confirmed tracks",
        (10, py + 54),
        sc,
        COLOURS["alligator_crack"],
    )
    text(
        out,
        "green = confirmed (3 of 5 frames)   dashed = horizon gate",
        (w - 520, py + 54),
        sc * 0.85,
        (200, 200, 200),
    )
    return out


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("video", type=Path)
    ap.add_argument("--record", type=Path, help="also write the screen here, at the video's rate")
    ap.add_argument("--headless", action="store_true", help="no window; with --record, a file only")
    ap.add_argument("--until-s", type=float, help="stop at this video time (a quick check)")
    args = ap.parse_args()

    start, end = LIVE["window_s"]
    gt = read_gt(ROOT / LIVE["gt"])
    intervals = [(r["start_s"], r["end_s"]) for r in gt]
    cap = cv2.VideoCapture(str(args.video))
    fps = cap.get(cv2.CAP_PROP_FPS)
    w, h = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)), int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    horizon_y = VCFG["horizon_frac"] * h
    first, last = int(round(start * fps)), int(round(end * fps))
    if args.until_s is not None:
        last = min(last, int(round(args.until_s * fps)))
    cap.set(cv2.CAP_PROP_POS_FRAMES, first)

    models = {m: Model(m, horizon_y) for m in CLASSES}
    print(
        f"{args.video.name}: {w}x{h} @ {fps:.0f} fps, "
        f"window {start}-{end} s, device {VCFG['device']}"
    )
    writer = None
    if not args.headless:
        cv2.namedWindow(NAME, cv2.WINDOW_NORMAL)
        cv2.resizeWindow(NAME, *LIVE["display"])
    tick, n_done = time.perf_counter(), 0
    stats = {"fps": 0.0, "P_ms": 0.0, "B_ms": 0.0, "P_confirmed": 0, "B_confirmed": 0}
    for n in range(first, last):
        ok, frame = cap.read()
        if not ok:
            break
        t_s = n / fps
        dets = []
        for m in models.values():
            dets += m.step(frame, n)
        n_done += 1
        stats["fps"] = n_done / (time.perf_counter() - tick)
        stats.update({f"{k}_ms": m.ms for k, m in models.items()})
        stats.update({f"{k}_confirmed": len(m.ever) for k, m in models.items()})
        live = score_tracks(
            models["P"].confirmed_tracks(),
            [iv for iv in intervals if iv[1] <= t_s],
            fps,
            (start, end),
        )
        stats["passed"], stats["caught"] = live["potholes"], live["hit"]
        k_in_view = next((i + 1 for i, (a, b) in enumerate(intervals) if a <= t_s < b), 0)
        img = draw(frame, dets, t_s, gt, k_in_view, stats, horizon_y)
        if args.record:
            if writer is None:
                args.record.parent.mkdir(parents=True, exist_ok=True)
                fourcc = cv2.VideoWriter_fourcc(*"mp4v")
                writer = cv2.VideoWriter(
                    str(args.record), fourcc, fps, (img.shape[1], img.shape[0])
                )
            writer.write(img)
        if not args.headless:
            cv2.imshow(NAME, img)
            if cv2.waitKey(1) & 0xFF in (27, ord("q")):
                break

    # Score the stretch actually played: a run stopped early must not count the potholes it
    # never reached as misses, nor spread its false alarms over minutes it did not watch.
    played_end = (first + n_done) / fps
    played = [iv for iv in intervals if iv[0] < played_end]
    p = score_tracks(models["P"].confirmed_tracks(), played, fps, (start, played_end))
    summary = {
        "video": args.video.name,
        "window_s": [start, round(played_end, 2)],
        "device": VCFG["device"],
        "frames": n_done,
        "processing_fps": round(stats["fps"], 2),
        "P": {
            k: p[k]
            for k in (
                "potholes",
                "hit",
                "tracks_in_window",
                "duplicates",
                "false_alarms",
                "false_alarms_per_min",
            )
        },
        "B_confirmed_crack_tracks": len(models["B"].ever),
    }
    out = ROOT / "runs" / "video_live" / args.video.stem / "live_summary.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(summary, indent=1))
    print(json.dumps(summary, indent=1))
    end_line = (
        f"Model P caught {p['hit']} of {p['potholes']} counted potholes; "
        f"{p['false_alarms']} false alarms ({p['false_alarms_per_min']:.1f} per minute)"
    )
    print(end_line)
    if writer is not None or not args.headless:
        card = img.copy()
        cv2.rectangle(
            card,
            (0, card.shape[0] // 2 - 40),
            (card.shape[1], card.shape[0] // 2 + 30),
            (20, 20, 20),
            -1,
        )
        text(
            card,
            end_line,
            (20, card.shape[0] // 2 + 5),
            LIVE["font_scale"] * 1.4,
            (255, 255, 255),
            2,
        )
        for _ in range(int(LIVE["end_hold_s"] * fps)):
            if writer is not None:
                writer.write(card)
        if not args.headless:
            cv2.imshow(NAME, card)
            cv2.waitKey(int(LIVE["end_hold_s"] * 1000))
    if writer is not None:
        writer.release()
    cap.release()
    cv2.destroyAllWindows()


if __name__ == "__main__":
    main()
