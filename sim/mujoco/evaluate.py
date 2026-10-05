"""Step 4: what the drive found against what was there, and what a budget would repair.

- **Detection.** A confirmed track hits an instance when, in some frame, its box overlaps the
  instance's projected box by more than `end.iou_min` and the classes agree. Recall per class
  is the share of instances that came into view nearer than the gate and were hit. A false
  alarm is a confirmed track that never hit an instance of its own class, counted per
  kilometre driven.
- **Repair plan.** Each segment becomes a `certain_road.survey.allocation.Segment` with its
  vision-estimated PCI. Its cost is D079's: mobilisation plus `cost_per_m2` times the
  reference distressed area. `allocate_optimal` and `allocate_greedy_worst_first` choose under
  the same budget. Each plan is then scored on D079's two objectives, both against the
  reference PCI: the true benefit repaired, and how many of the true worst N it repairs.
"""

from __future__ import annotations

import json
from pathlib import Path

from certain_road.survey.allocation import (
    Segment,
    allocate_greedy_worst_first,
    allocate_optimal,
    total_cost,
)
from sim.mujoco.drive import PROJECT, gate_row
from sim.mujoco.road import CLASSES, Road
from sim.mujoco.scene import design_camera
from sim.mujoco.survey import SegmentResult, gt_boxes_by_id

POLICIES = {"optimiser": allocate_optimal, "worst-first": allocate_greedy_worst_first}


def iou(a, b) -> float:
    ix = max(0.0, min(a[2], b[2]) - max(a[0], b[0]))
    iy = max(0.0, min(a[3], b[3]) - max(a[1], b[1]))
    inter = ix * iy
    union = (a[2] - a[0]) * (a[3] - a[1]) + (b[2] - b[0]) * (b[3] - b[1]) - inter
    return inter / union if union > 0 else 0.0


def detection_scores(road: Road, records: list[dict], cfg: dict, cam: dict | None = None) -> dict:
    """Per-class recall and false alarms per km of the confirmed tracks in a drive log."""
    cam = cam or design_camera()
    e, horizon = cfg["end"], gate_row(cam)
    reach = PROJECT["edge"]["detect_range_m"] + 1.0
    by_id = {i.id: i for i in road.instances}
    seen: set[int] = set()
    hit: set[int] = set()
    tracks: dict[tuple[str, int], tuple[str, bool]] = {}  # (model, id) -> (class, hit?)
    for k, r in enumerate(records):
        confirmed = [d for d in r["dets"] if d["confirmed"]]
        if not confirmed and k % e["seen_every_frames"]:
            continue
        gts = gt_boxes_by_id(road, r["x_m"], cam, cfg, max_m=reach)
        for gid, b in gts:
            if b[4] >= horizon:
                seen.add(gid)
        for d in confirmed:
            key = (d["model"], d["track"])
            box = (d["x1"], d["y1"], d["x2"], d["y2"])
            mine = [
                gid
                for gid, b in gts
                if by_id[gid].cls == d["cls"] and iou(box, b[1:]) > e["iou_min"]
            ]
            hit.update(mine)
            tracks[key] = (d["cls"], tracks.get(key, (d["cls"], False))[1] or bool(mine))
    seen |= hit  # a hit instance was in view, whatever its own box said
    km = (records[-1]["x_m"] - records[0]["x_m"]) / 1000 if records else 0.0
    out = {"km": round(km, 4), "per_class": {}}
    for c in CLASSES:
        n = sum(by_id[i].cls == c for i in seen)
        h = sum(by_id[i].cls == c for i in hit)
        fa = sum(1 for cls, ok in tracks.values() if cls == c and not ok)
        out["per_class"][c] = {
            "instances": n,
            "hit": h,
            "recall": round(h / n, 4) if n else None,
            "false_alarm_tracks": fa,
            "false_alarms_per_km": round(fa / km, 2) if km else None,
        }
    return out


def repair_plan(segments: list[SegmentResult], cfg: dict, budget_frac: float | None = None) -> dict:
    """The optimiser and worst-first under one budget, each scored on D079's two objectives."""
    a, e = PROJECT["allocation"], cfg["end"]
    frac = e["budget_frac"] if budget_frac is None else budget_frac
    cost = {s.index: a["mobilisation_cost"] + a["cost_per_m2"] * s.area_ref_m2 for s in segments}
    segs = [Segment(s.index, s.vision_estimated_pci, cost[s.index]) for s in segments]
    budget = frac * sum(cost.values())
    benefit = {s.index: 100.0 - s.pci_ref for s in segments}
    worst = [s.index for s in sorted(segments, key=lambda s: (s.pci_ref, s.index))][: e["worst_n"]]
    out = {"budget_frac": frac, "budget": round(budget, 2), "worst": worst, "plans": {}}
    for name, policy in POLICIES.items():
        chosen = policy(segs, budget)
        out["plans"][name] = {
            "chosen": chosen,
            "cost": round(total_cost(segs, chosen), 2),
            "true_benefit": round(sum(benefit[i] for i in chosen), 2),
            "worst_covered": sum(i in chosen for i in worst),
        }
    return out


def summarise(road: Road, cfg: dict, run_dir: Path, budget_frac: float | None = None) -> dict:
    """Everything the end screen shows, from a run's logs; also written to end.json."""
    records = [json.loads(line) for line in (run_dir / "detections.jsonl").open()]
    survey = json.loads((run_dir / "survey.json").read_text())
    segments = [SegmentResult(**s) for s in survey["segments"]]
    end = {
        "preset": road.preset,
        "seed": road.seed,
        "length_m": road.length_m,
        "segments": survey["segments"],
        "drift_alarm_m": survey["drift"]["alarm_m"],
        "detection": detection_scores(road, records, cfg),
        "repair": repair_plan(segments, cfg, budget_frac),
    }
    (run_dir / "end.json").write_text(json.dumps(end, indent=1))
    return end
