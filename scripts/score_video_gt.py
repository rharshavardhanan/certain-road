"""Score each model's confirmed video tracks against hand-counted pothole intervals.

D075 counts tracks, not potholes, and "P 100 tracks vs B 9" cannot say which model
finds more potholes and which merely fires more (D081). One annotator's intervals
over a window turn that into potholes caught of those present, and false alarms
per minute.

**The rule.** Tracks confirmed inside the window are taken in order of first
frame. A track whose span `[first_frame, last_frame]` overlaps a GT interval not
yet hit is a **hit** on the earliest-starting such interval; one track is never
more than one hit. A track overlapping only intervals already hit is a
**duplicate** (an ID switch or a second box on one pothole). A track overlapping
no interval is a **false alarm**.

    uv run python scripts/score_video_gt.py configs/eval/gt/<stem>_<who>.csv --start S --end E

The CSV is `start_s,end_s,note`, one line per pothole; lines starting with `#`
are comments. Writes `results/video/<stem>/gt_score.json`.
"""

import argparse
import csv
import hashlib
import json
import statistics
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from certain_road.core.paths import repo_root  # noqa: E402

CAVEATS = [
    "One annotator. Nothing here measures agreement between annotators, and what counts "
    "as a pothole is that annotator's judgement.",
    "Interval-only, no spatial matching: a track counts as a hit if it overlaps a GT "
    "interval in time, wherever its box sits in the frame. A box on something else while a "
    "pothole is in view scores as a hit, so hits are an upper bound on correct detections.",
    "Tracks, not potholes (D075): duplicates expose ID switches and double boxes; a merge "
    "that holds two potholes in one track shows up as a miss.",
    "One 60 s window of one video, chosen for pothole content and excluding the flooded "
    "stretch (D080). It describes discrete potholes on this road, not the drive.",
]


def score_tracks(
    tracks: dict[str, dict],
    intervals: list[tuple[float, float]],
    fps: float,
    window: tuple[float, float],
) -> dict:
    """Apply the hit / duplicate / false-alarm rule to one model's confirmed tracks."""
    start, end = window
    inside = [(tid, t) for tid, t in tracks.items() if start <= t["confirmed_at"] / fps < end]
    inside.sort(key=lambda kv: (kv[1]["first_frame"], kv[1]["confirmed_at"], kv[0]))

    hit_by: dict[int, str] = {}
    hits, duplicates, false_alarms = [], [], []
    for tid, t in inside:
        t0, t1 = t["first_frame"] / fps, (t["last_frame"] + 1) / fps
        overlapping = [i for i, (a, b) in enumerate(intervals) if t0 < b and a < t1]
        free = [i for i in overlapping if i not in hit_by]
        if free:
            hit_by[min(free, key=lambda i: intervals[i][0])] = tid
            hits.append(t)
        elif overlapping:
            duplicates.append(tid)
        else:
            false_alarms.append(tid)

    minutes = (end - start) / 60
    return {
        "potholes": len(intervals),
        "hit": len(hit_by),
        "tracks_in_window": len(inside),
        "duplicates": len(duplicates),
        "false_alarms": len(false_alarms),
        "false_alarms_per_min": len(false_alarms) / minutes,
        "median_frames_per_hit": statistics.median(t["frames_detected"] for t in hits)
        if hits
        else None,
        "intervals": [
            {"start_s": a, "end_s": b, "hit_by": hit_by.get(i)}
            for i, (a, b) in enumerate(intervals)
        ],
        "duplicate_tracks": duplicates,
        "false_alarm_tracks": false_alarms,
    }


def read_gt(path: Path) -> list[dict]:
    lines = [ln for ln in path.read_text().splitlines() if ln.strip() and not ln.startswith("#")]
    rows = list(csv.DictReader(lines))
    for r in rows:
        r["start_s"], r["end_s"] = float(r["start_s"]), float(r["end_s"])
        if not r["start_s"] < r["end_s"]:
            sys.exit(f"GT interval ends before it starts: {r}")
    return rows


def main() -> None:
    ap = argparse.ArgumentParser(description="Per-pothole scoring of confirmed video tracks")
    ap.add_argument("gt", type=Path)
    ap.add_argument("--start", type=float, required=True, help="window start, seconds")
    ap.add_argument("--end", type=float, required=True, help="window end, seconds")
    ap.add_argument("--stem", default="2DV-cYmIvT4")
    ap.add_argument("--models", nargs="+", default=["B", "P"])
    args = ap.parse_args()

    gt = read_gt(args.gt)
    outside = [r for r in gt if r["start_s"] >= args.end or r["end_s"] <= args.start]
    if outside:
        sys.exit(f"GT intervals outside the window {args.start}-{args.end} s: {outside}")
    intervals = [(r["start_s"], r["end_s"]) for r in gt]

    root = repo_root()
    models = {}
    for m in args.models:
        summary = json.loads(
            (root / "results" / "video" / args.stem / m / "summary.json").read_text()
        )
        r = score_tracks(
            summary["result"]["confirmed_tracks"],
            intervals,
            summary["video"]["fps"],
            (args.start, args.end),
        )
        for iv, row in zip(r["intervals"], gt, strict=True):
            iv["note"] = row.get("note", "")
        models[m] = r

    with args.gt.open("rb") as f:
        sha = hashlib.file_digest(f, "sha256").hexdigest()
    out = root / "results" / "video" / args.stem / "gt_score.json"
    out.write_text(
        json.dumps(
            {
                "gt": {"path": str(args.gt), "sha256": sha, "potholes": len(gt)},
                "window_s": [args.start, args.end],
                "models": models,
                "caveats": CAVEATS,
            },
            indent=2,
        )
        + "\n"
    )

    print(
        f"{'model':<6}{'hit/total':>11}{'duplicates':>12}{'FA':>5}{'FA/min':>8}"
        f"{'median frames/hit':>19}{'tracks':>8}"
    )
    for m, r in models.items():
        print(
            f"{m:<6}{r['hit']:>5}/{r['potholes']:<5}{r['duplicates']:>12}{r['false_alarms']:>5}"
            f"{r['false_alarms_per_min']:>8.1f}{str(r['median_frames_per_hit']):>19}"
            f"{r['tracks_in_window']:>8}"
        )
    print(f"wrote {out.relative_to(root)}")


if __name__ == "__main__":
    main()
