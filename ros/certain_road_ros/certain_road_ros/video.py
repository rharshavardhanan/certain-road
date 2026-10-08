"""A road video as the demo's camera: its ground truth, per-frame facts and the decisions' score.

Pure: no ROS and no OpenCV, so it is tested anywhere. `video_node` plays the clip; this
module answers which hand-counted potholes are in view at a video time, what the overlay's
ground-truth strip says, how one frame's facts travel on /video/frame_info, and how the
planner's decisions line up with the ground truth afterwards.

**Open loop.** A recording cannot be steered. The planner decides on every frame and its
commands leave as /cmd_vel and CAN frames, but nothing it sends changes the next frame. The
score is therefore of decisions, not of avoidance: did the planner leave NORMAL while a
counted pothole was in view, and how often did it start a reaction while none was.

The ground truth is `configs/eval/gt/<clip>_<who>.csv`, read by the rule
`scripts/score_video_gt.py`'s `read_gt` uses (a test pins that the two agree): one line per
pothole, `start_s,end_s,note`; `#` lines are comments. It is interval-only, with no boxes,
so "in view" is a time, not a place in the frame.
"""

from __future__ import annotations

import csv
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

NORMAL = "normal"
# Steering away or stopping. WARNING (slow down, keep going) leaves NORMAL but is not one.
MANOEUVRES = frozenset({"avoid_left", "avoid_right", "stop"})


@dataclass(frozen=True)
class Interval:
    """One counted pothole: first clear sighting to leaving the frame, in video seconds."""

    start_s: float
    end_s: float
    note: str


def read_intervals(path: Path) -> list[Interval]:
    lines = [ln for ln in path.read_text().splitlines() if ln.strip() and not ln.startswith("#")]
    out = []
    for row in csv.DictReader(lines):
        iv = Interval(float(row["start_s"]), float(row["end_s"]), row["note"])
        if not iv.start_s < iv.end_s:
            raise ValueError(f"ground-truth interval ends before it starts: {row}")
        out.append(iv)
    return out


def in_view(intervals: list[Interval], t_s: float) -> tuple[int, ...]:
    """1-based numbers of the counted potholes in view at video time `t_s`, [start, end).

    Intervals overlap where several potholes are in frame at once, so this is a tuple;
    `scripts/live_video.py` showed only the first."""
    return tuple(i + 1 for i, iv in enumerate(intervals) if iv.start_s <= t_s < iv.end_s)


def gt_strip(in_view: tuple[int, ...], total: int | None) -> str:
    """The ground-truth strip's text, in `scripts/live_video.py`'s words."""
    if total is None:
        return "no ground truth for this clip"
    if not in_view:
        return "ground truth: no counted pothole in view"
    numbers = ", ".join(f"#{k}" for k in in_view)
    noun = "pothole" if len(in_view) == 1 else "potholes"
    return f"GROUND TRUTH: {noun} {numbers} of {total} in view"


@dataclass(frozen=True)
class FrameInfo:
    """What one video frame is, beside its pixels: published on /video/frame_info with the
    image's stamp, so perception can draw the strip and the planner can log video time."""

    clip: str
    frame: int
    video_time_s: float
    gt_in_view: tuple[int, ...]
    gt_total: int | None  # None: no ground truth for this clip
    pacing: str  # the overlay's short pacing label
    lockstep: bool  # each frame waits for the last one's detections: video time is the clock
    notice: str  # the open-loop notice
    credit: str

    @property
    def strip(self) -> str:
        return gt_strip(self.gt_in_view, self.gt_total)

    def to_values(self) -> dict[str, str]:
        return {
            "clip": self.clip,
            "frame": str(self.frame),
            "video_time_s": repr(self.video_time_s),
            "gt_in_view": ",".join(str(k) for k in self.gt_in_view),
            "gt_total": "" if self.gt_total is None else str(self.gt_total),
            "pacing": self.pacing,
            "lockstep": "1" if self.lockstep else "0",
            "notice": self.notice,
            "credit": self.credit,
        }

    @classmethod
    def from_values(cls, values: dict[str, str]) -> FrameInfo:
        seen, total = values["gt_in_view"], values["gt_total"]
        return cls(
            clip=values["clip"],
            frame=int(values["frame"]),
            video_time_s=float(values["video_time_s"]),
            gt_in_view=tuple(int(k) for k in seen.split(",")) if seen else (),
            gt_total=int(total) if total else None,
            pacing=values["pacing"],
            lockstep=values["lockstep"] == "1",
            notice=values["notice"],
            credit=values["credit"],
        )


def score_decisions(rows: list[dict], gt_total: int | None) -> dict:
    """How the planner's per-frame decisions line up with the counted potholes.

    `rows` are the decisions made on video frames, in order, each with `frame`,
    `video_time_s`, `gt_in_view` and `state`. Staleness-failsafe decisions belong to no
    frame and are not rows. A **reaction onset** is a step from NORMAL to any other state;
    a **manoeuvre onset** is a step into AVOID_LEFT, AVOID_RIGHT or STOP from outside them.
    The planner starts in NORMAL, so a first row that is not NORMAL is an onset. An onset
    "inside" ground truth is one on a frame with a counted pothole in view.
    """
    reactions, manoeuvres = [], []
    prev = NORMAL
    per_pothole: dict[int, dict] = {}
    for r in rows:
        state, seen, t = r["state"], tuple(r["gt_in_view"]), r["video_time_s"]
        onset = {"frame": r["frame"], "video_time_s": t, "state": state, "gt_in_view": list(seen)}
        if prev == NORMAL and state != NORMAL:
            reactions.append(onset)
        if prev not in MANOEUVRES and state in MANOEUVRES:
            manoeuvres.append(onset)
        prev = state
        for k in seen:
            p = per_pothole.setdefault(k, {"pothole": k, "in_view_s": [t, t], "states": set()})
            p["in_view_s"][1] = t
            p["states"].add(state)

    potholes = []
    for k in sorted(per_pothole):
        p = per_pothole[k]
        states = p.pop("states")
        p["left_normal"] = states != {NORMAL}
        p["manoeuvred"] = bool(states & MANOEUVRES)
        p["states"] = sorted(states)
        potholes.append(p)

    def outside(onsets: list[dict]) -> list[dict]:
        return [o for o in onsets if not o["gt_in_view"]]

    in_gt = Counter(r["state"] for r in rows if r["gt_in_view"])
    out_gt = Counter(r["state"] for r in rows if not r["gt_in_view"])
    times = [r["video_time_s"] for r in rows]
    return {
        "frames": len(rows),
        "video_time_s": [min(times), max(times)] if times else None,
        "gt_potholes": gt_total,
        "gt_potholes_in_processed_frames": len(potholes),
        "gt_potholes_left_normal": sum(p["left_normal"] for p in potholes),
        "gt_potholes_manoeuvred": sum(p["manoeuvred"] for p in potholes),
        "reaction_onsets": len(reactions),
        "reaction_onsets_outside_gt": len(outside(reactions)),
        "manoeuvre_onsets": len(manoeuvres),
        "manoeuvre_onsets_outside_gt": len(outside(manoeuvres)),
        "frames_by_state_gt_in_view": dict(sorted(in_gt.items())),
        "frames_by_state_no_gt_in_view": dict(sorted(out_gt.items())),
        "potholes": potholes,
        "reaction_onset_list": reactions,
        "manoeuvre_onset_list": manoeuvres,
    }
