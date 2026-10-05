"""The live and end screens render their edge cases rather than crash mid-demo.

No weights or GL: the drive loop is stood in for by its records and a survey fed by hand.
"""

import types

import numpy as np

from sim.mujoco.drive import Det, FrameRecord
from sim.mujoco.evaluate import repair_plan
from sim.mujoco.road import CLASSES, Road, load_config
from sim.mujoco.scene import design_camera
from sim.mujoco.screen import Screen, render_end
from sim.mujoco.survey import Survey

CFG = load_config()
CAM = design_camera()
ROAD = Road("good", 0, 120.0, 3.5, 1.75, ())
SIZE = (CFG["screen"]["size"][1], CFG["screen"]["size"][0], 3)


def test_live_screen_draws_detections_segments_and_a_drift_alarm():
    survey = Survey(ROAD, CFG, CAM)
    drv = types.SimpleNamespace(
        survey=survey, horizon=297.6, cam=CAM, drift=types.SimpleNamespace(log_threshold=9.21)
    )
    screen = Screen(ROAD, CFG, CAM, samples_total=21, per_segment=survey.per_segment)
    bgr = np.full((CAM["h"], CAM["w"], 3), 120, np.uint8)
    dets = [Det("P", "pothole", 0.6, 600, 400, 700, 450, 1, True)]
    for k in range(300):
        sampled = k % 27 == 0
        rec = FrameRecord(k, k * 5 / 27, k / 30, sampled, dets, {})
        if sampled:
            rec.drift = {"score": 0.99, "log_m": k / 20, "alarmed": k / 20 > 9.21}
            rec.closed = survey.add(k, rec.x_m, rec.t_s, [("pothole", 0.6, 600, 400, 700, 450)])
        img = screen.update(rec, bgr, drv)
    assert img.shape == SIZE and img.dtype == np.uint8
    assert screen.alarm_m is not None and screen.tracks["pothole"] == {1}
    assert survey.segments  # a segment closed, so the caption and map drew it


def test_end_screen_with_nothing_to_repair_and_a_class_never_seen():
    survey = Survey(ROAD, CFG, CAM)
    for k in range(20):
        survey.add(k, k * 5.0, k * 0.9, [])
    plan = repair_plan(survey.segments, CFG)
    assert all(p["true_benefit"] == 0 for p in plan["plans"].values())
    empty = {
        "instances": 0,
        "hit": 0,
        "recall": None,
        "false_alarm_tracks": 0,
        "false_alarms_per_km": None,
    }
    end = {
        "segments": [s.__dict__ for s in survey.segments],
        "drift_alarm_m": None,
        "detection": {"km": 0.0, "per_class": dict.fromkeys(CLASSES, empty)},
        "repair": plan,
    }
    assert render_end(end, ROAD, CFG).shape == SIZE
