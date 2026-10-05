"""The end screen's numbers: detection against ground truth, and the repair plan.

The plan must be certain_road.survey.allocation's own choice on the survey's segments, priced
as D079 prices them. Pure arithmetic: no weights, no GL and no data/ folder.
"""

import pytest

from certain_road.survey.allocation import (
    Segment,
    allocate_greedy_worst_first,
    allocate_optimal,
)
from sim.mujoco.drive import PROJECT, gate_row
from sim.mujoco.evaluate import detection_scores, iou, repair_plan
from sim.mujoco.road import Road, generate, load_config
from sim.mujoco.scene import design_camera
from sim.mujoco.survey import SegmentResult, gt_boxes_by_id

FAKE = {
    "pothole": [("p1", 1.3, 0, 900, 700), ("p2", 1.1, 0, 800, 720)],
    "linear_crack": [("l1", 3.5, 2000, 3000, 860)],
    "alligator_crack": [("a1", 1.33, 2000, 2700, 2025)],
}
CFG = load_config()
CAM = design_camera()


def det(cls, box, track, confirmed=True):
    model = "P" if cls == "pothole" else "B"
    return dict(zip(("x1", "y1", "x2", "y2"), box, strict=True)) | {
        "model": model,
        "cls": cls,
        "track": track,
        "confirmed": confirmed,
        "score": 0.9,
    }


def test_iou():
    assert iou((0, 0, 2, 2), (0, 0, 2, 2)) == 1.0
    assert iou((0, 0, 2, 2), (1, 0, 3, 2)) == pytest.approx(1 / 3)
    assert iou((0, 0, 1, 1), (2, 2, 3, 3)) == 0.0


def test_a_perfect_tracker_finds_everything_and_raises_no_false_alarm():
    road = generate("poor", 0, FAKE)
    horizon, reach = gate_row(CAM), PROJECT["edge"]["detect_range_m"] + 1.0
    records = []
    for k in range(int((road.length_m - 15) / 0.5)):
        x = k * 0.5
        gts = gt_boxes_by_id(road, x, CAM, CFG, max_m=reach)
        dets = [det(b[0], b[1:], gid) for gid, b in gts if b[4] >= horizon]
        records.append({"x_m": x, "dets": dets})
    out = detection_scores(road, records, CFG, CAM)
    for c, r in out["per_class"].items():
        assert r["instances"] > 0, c
        assert r["recall"] == 1.0 and r["false_alarm_tracks"] == 0, (c, r)


def test_a_track_on_bare_road_is_a_false_alarm_per_km():
    road = Road("test", 0, 600.0, 3.5, 1.75, ())
    records = [{"x_m": x, "dets": [det("pothole", (600, 500, 700, 540), 7)]} for x in range(501)]
    out = detection_scores(road, records, CFG, CAM)
    p = out["per_class"]["pothole"]
    assert out["km"] == 0.5 and p["instances"] == 0 and p["recall"] is None
    assert p["false_alarm_tracks"] == 1 and p["false_alarms_per_km"] == 2.0


def seg(i, pci, ref, area):
    d = {c: (0.0, "vision_density_pct") for c in ("linear_crack", "alligator_crack", "pothole")}
    counts = dict.fromkeys(d, 0)
    return SegmentResult(i, 50.0 * i, 50.0 * i + 50, 10, counts, pci, "x", d, ref, "x", d, area)


def test_the_plan_is_the_real_allocators_choice_priced_as_d079():
    a = PROJECT["allocation"]
    segments = [
        seg(0, 95.0, 97.0, 0.5),
        seg(1, 40.0, 35.0, 12.0),
        seg(2, 70.0, 80.0, 4.0),
        seg(3, 30.0, 55.0, 20.0),
        seg(4, 60.0, 30.0, 6.0),
    ]
    out = repair_plan(segments, CFG, budget_frac=0.45)
    cost = [a["mobilisation_cost"] + a["cost_per_m2"] * s.area_ref_m2 for s in segments]
    segs = [
        Segment(s.index, s.vision_estimated_pci, c) for s, c in zip(segments, cost, strict=True)
    ]
    budget = 0.45 * sum(cost)
    assert out["budget"] == pytest.approx(budget, abs=0.01)
    assert out["plans"]["optimiser"]["chosen"] == allocate_optimal(segs, budget)
    assert out["plans"]["worst-first"]["chosen"] == allocate_greedy_worst_first(segs, budget)
    # true worst 3 by reference PCI: 4 (30), 1 (35), 3 (55)
    assert out["worst"] == [4, 1, 3]
    for p in out["plans"].values():
        assert p["cost"] <= budget
        assert p["worst_covered"] == sum(i in p["chosen"] for i in (4, 1, 3))
        assert p["true_benefit"] == pytest.approx(
            sum(100 - segments[i].pci_ref for i in p["chosen"])
        )
