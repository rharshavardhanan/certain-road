"""The live survey: D006's ROI counts each instance once, and scores come from certain_road.survey.

Pure geometry and arithmetic: no weights, no GL and no data/ folder.
"""

import dataclasses
import math

import pandas as pd
import pytest

from certain_road.core.geometry import ground_point, project
from certain_road.survey import scoring
from certain_road.survey.segment import segment_drive
from sim.mujoco.road import Road, generate, load_config
from sim.mujoco.scene import design_camera
from sim.mujoco.survey import PROJECT, Survey, gt_boxes, in_roi, roi, survey_camera

# (name, aspect, natural px/m or 0, crop long px, crop short px), as in test_mujoco_road
FAKE = {
    "pothole": [("p1", 1.3, 0, 900, 700), ("p2", 1.1, 0, 800, 720)],
    "linear_crack": [("l1", 3.5, 2000, 3000, 860)],
    "alligator_crack": [("a1", 1.33, 2000, 2700, 2025)],
}
CFG = load_config()
CAM = design_camera()
CAMERA = survey_camera(CAM)
KW = {"f": CAMERA.f, "cx": CAMERA.cx, "cy": CAMERA.cy, "cam_h": CAMERA.cam_h, "pitch": CAMERA.pitch}
STEP = PROJECT["edge"]["sample_every_m"]
SC = PROJECT["scoring"]


def box(cls: str, fwd: float, left: float, length: float, width: float) -> tuple:
    """Image box round a ground rectangle `length` deep and `width` wide, nearest edge at fwd."""
    pts = [project(fwd + a, left + b, **KW) for a in (0, length) for b in (-width / 2, width / 2)]
    us, vs = [p[0] for p in pts], [p[1] for p in pts]
    return (cls, min(us), min(vs), max(us), max(vs))


def test_roi_starts_past_the_frame_bottom_and_ends_inside_the_gate():
    """A box cut off by the frame's bottom edge has its base on that edge, not on the damage."""
    near, far, half = roi(CFG)
    assert near > ground_point(CAM["w"] / 2, CAM["h"], **KW)[0]
    assert far <= PROJECT["edge"]["detect_range_m"]
    assert far - near == STEP and half == SC["lane_width_m"] / 2


def test_each_instance_is_counted_by_exactly_one_sample():
    """D006: the ROIs tile the road, so no damage is counted twice and none is skipped."""
    road = generate("poor", 0, FAKE)
    xs = [k * STEP for k in range(int(road.length_m / STEP))]
    near = roi(CFG)[0]
    central = 0
    for inst in road.instances:
        one = dataclasses.replace(road, instances=(inst,))
        hits = sum(in_roi(b, CAMERA, CFG) for x in xs for b in gt_boxes(one, x, CAM, CFG))
        assert hits <= 1, inst
        if abs(inst.y_m - road.drive_lane_y) < 0.75 and inst.bbox[0] < xs[-1] + near:
            assert hits == 1, inst
            central += 1
    assert central >= 10


def test_segment_score_is_certain_road_survey_on_the_same_boxes():
    survey = Survey(Road("test", 0, 120.0, 3.5, 1.75, ()), CFG)
    pot = box("pothole", 4.0, 0.3, 0.6, 0.7)
    crack = box("alligator_crack", 5.0, -0.4, 2.0, 1.5)
    beyond = box("pothole", 10.0, 0.0, 0.8, 0.8)  # past the ROI: a later sample counts it
    res = None
    for k in range(10):
        res = survey.add(k, k * STEP, k * 0.9, [(b[0], 0.8, *b[1:]) for b in (pot, crack, beyond)])
    assert res is not None and res.n_samples == 10

    deducts = {}
    for c, b in (("pothole", pot), ("alligator_crack", crack), ("linear_crack", None)):
        fp = [scoring.box_footprint_m2(*b[1:], CAMERA)] * 10 if b else []
        value, _ = scoring.segment_distress(
            fp, segment_m=SC["segment_m"], lane_width_m=SC["lane_width_m"]
        )
        deducts[c] = scoring.deduct_value(value, SC["deduct_weights"][c])
    want = scoring.vision_estimated_pci(deducts)
    assert res.vision_estimated_pci == round(want, 2)
    assert res.band == scoring.band(want)

    # The weights and areas really are the project's: pin one class by hand.
    pot_pct = 10 * scoring.box_footprint_m2(*pot[1:], CAMERA) / (50 * 3.5) * 100
    assert deducts["pothole"] == pytest.approx(30 * math.log10(1 + pot_pct))

    log = pd.DataFrame(
        {"frame_id": [str(k) for k in range(10)], "timestamp_s": [k * 0.9 for k in range(10)]}
    ).assign(survey_date=pd.Timestamp("2026-10-05").date())
    dets = pd.DataFrame(
        [
            {"frame_id": str(k), "class_name": c, "score": 0.8}
            for k in range(10)
            for c in ("pothole", "alligator_crack")
        ]
    )
    row = segment_drive(dets, log, frames_per_segment=10).iloc[0]
    assert res.counts == {
        "linear_crack": row["n_linear_crack"],
        "alligator_crack": row["n_alligator_crack"],
        "pothole": row["n_pothole"],
    }


def test_a_perfect_detector_scores_exactly_the_reference():
    """Ground truth and detections share every step, so feeding one as the other agrees exactly."""
    road = generate("poor", 1, FAKE)
    survey = Survey(road, CFG)
    for k in range(int(road.length_m / STEP)):
        survey.add(
            k, k * STEP, k * 0.9, [(b[0], 1.0, *b[1:]) for b in gt_boxes(road, k * STEP, CAM, CFG)]
        )
    survey.finish()
    assert len(survey.segments) >= 8
    assert any(s.pci_ref < 70 for s in survey.segments)  # the test sees real damage
    for s in survey.segments:
        assert s.vision_estimated_pci == s.pci_ref and s.band == s.band_ref


def test_undamaged_road_scores_100_and_a_partial_segment_uses_its_own_length():
    survey = Survey(Road("test", 0, 80.0, 3.5, 1.75, ()), CFG)
    pot = box("pothole", 4.0, 0.0, 0.6, 0.6)
    for k in range(13):
        survey.add(k, k * STEP, k * 0.9, [(pot[0], 0.7, *pot[1:])])
    last = survey.finish()
    first = survey.segments[0]
    assert first.pci_ref == 100.0 and first.band_ref == "Good"
    assert last.n_samples == 3 and last.x1_m - last.x0_m == pytest.approx(3 * STEP)
    pct = 3 * scoring.box_footprint_m2(*pot[1:], CAMERA) / (3 * STEP * 3.5) * 100
    assert last.distress["pothole"][0] == pytest.approx(pct, abs=1e-4)
