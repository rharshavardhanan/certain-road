"""The detection gallery's pure parts: where a box is on the road, and the exact frame replay.

No weights, no GL and no data/ folder: a perfect tracker is built from the ground truth, as
test_mujoco_evaluate does, and the replay is checked on the camera's noise stream alone.
"""

import math
import statistics

import numpy as np
import pytest

from certain_road.core.geometry import project
from sim.mujoco.camera import NOISE_PAD, Camera
from sim.mujoco.drive import PROJECT, gate_row
from sim.mujoco.gallery import (
    base_ground,
    bbox_distance,
    compare,
    lane_of,
    replay,
    segment_of,
    summarise_tracks,
    track_frames,
)
from sim.mujoco.road import generate, load_config
from sim.mujoco.scene import design_camera
from sim.mujoco.survey import gt_boxes_by_id, ipm_kw, survey_camera

FAKE = {
    "pothole": [("p1", 1.3, 0, 900, 700), ("p2", 1.1, 0, 800, 720)],
    "linear_crack": [("l1", 3.5, 2000, 3000, 860)],
    "alligator_crack": [("a1", 1.33, 2000, 2700, 2025)],
}
CFG = load_config()
CAM = design_camera()
STEP_M = 0.5
SAMPLE_EVERY = 10  # every 5 m at this step, as the drive samples every edge.sample_every_m


def perfect_drive(road, until_m: float):
    """Records a perfect detector and tracker would log: the projected ground truth, confirmed."""
    horizon, reach = gate_row(CAM), PROJECT["edge"]["detect_range_m"] + 1.0
    records = []
    for k in range(int(until_m / STEP_M)):
        x = k * STEP_M
        gts = gt_boxes_by_id(road, x, CAM, CFG, max_m=reach)
        dets = [
            {
                "model": "P" if b[0] == "pothole" else "B",
                "cls": b[0],
                "track": gid,
                "confirmed": True,
                "score": 0.9,
                "x1": b[1],
                "y1": b[2],
                "x2": b[3],
                "y2": b[4],
            }
            for gid, b in gts
            if b[4] >= horizon
        ]
        sampled = k % SAMPLE_EVERY == 0
        records.append(
            {
                "frame": k,
                "x_m": x,
                "sampled": sampled,
                "dets": dets,
                "survey": dets if sampled else [],
            }
        )
    return records


def test_lanes_keep_left():
    assert lane_of(1.75, 3.5) == "left lane (driving)"
    assert lane_of(0.0, 3.5) == "left lane (driving)"
    assert lane_of(-0.1, 3.5) == "right lane (oncoming)"
    assert lane_of(3.6, 3.5) == "left verge"
    assert lane_of(-3.6, 3.5) == "right verge"


def test_segment_of_uses_the_scored_ground():
    segs = [{"index": 0, "x0_m": 3.0, "x1_m": 53.0}, {"index": 1, "x0_m": 53.0, "x1_m": 103.0}]
    assert segment_of(2.0, segs) is None
    assert segment_of(3.0, segs) == 0
    assert segment_of(53.0, segs) == 1
    assert segment_of(103.0, segs) is None


def test_bbox_distance():
    box = (10.0, -1.0, 12.0, 1.0)
    assert bbox_distance(11.0, 0.0, box) == 0.0
    assert bbox_distance(13.0, 0.0, box) == pytest.approx(1.0)
    assert bbox_distance(13.0, 2.0, box) == pytest.approx(math.sqrt(2.0))


def test_base_ground_inverts_the_projection():
    drive_y = 1.75
    for fwd, left in ((4.0, 0.0), (7.5, -1.2), (11.0, 2.0)):
        u, v = project(fwd, left, **ipm_kw(survey_camera(CAM)))
        x, y = base_ground((u - 20, v - 30, u + 20, v), 100.0, CAM, drive_y)
        assert x == pytest.approx(100.0 + fwd, abs=1e-6)
        assert y == pytest.approx(drive_y + left, abs=1e-6)


def test_a_perfect_tracker_is_placed_on_its_instance():
    road = generate("poor", 0, FAKE)
    records = perfect_drive(road, 120.0)
    segments = [{"index": i, "x0_m": 3.0 + 50 * i, "x1_m": 53.0 + 50 * i} for i in range(3)]
    tracks = summarise_tracks(road, records, segments, CFG, CAM)
    assert tracks and len(tracks) == len(track_frames(records))
    by_id = {i.id: i for i in road.instances}
    errors = []
    for t in tracks:
        assert not t["false_alarm"] and t["hit_ids"] == [t["track"]], t
        loc = t["location"]
        inst = by_id[t["track"]]
        errors.append(loc["error_to_match_m"])
        assert (
            loc["nearest_instance"]["id"] == inst.id or loc["nearest_instance"]["distance_m"] == 0
        )
        assert (loc["lateral_m"] >= 0) == (inst.y_m >= 0) or abs(inst.y_m) < inst.width_m
    assert statistics.median(errors) <= 0.05
    assert any(t["counted_in_survey"] for t in tracks)


def test_replay_reproduces_the_frames_of_a_sequential_drive():
    class Fake:
        def __init__(self):
            self.rng = np.random.default_rng(7)

        def skip_frames(self, n):
            for _ in range(n):
                self.rng.integers(0, NOISE_PAD, 2)

        def frame(self, x):
            return (x, tuple(self.rng.integers(0, NOISE_PAD, 2)))

    seq = Fake()
    drive = [seq.frame(k * 0.1) for k in range(12)]
    wanted = {9: 0.9, 2: 0.2, 5: 0.5}
    got = dict(replay(Fake(), wanted))
    assert got == {k: drive[k] for k in wanted}


def test_camera_skip_frames_draws_what_frame_draws():
    cam = Camera.__new__(Camera)  # no renderer: only the noise stream is under test
    cam.rng = np.random.default_rng([0, 37])
    cam.skip_frames(4)
    ref = np.random.default_rng([0, 37])
    for _ in range(4):
        ref.integers(0, NOISE_PAD, 2)
    assert list(cam.rng.integers(0, NOISE_PAD, 2)) == list(ref.integers(0, NOISE_PAD, 2))


def test_compare_reports_identical_boxes():
    logged = [
        {"model": "P", "cls": "pothole", "score": 0.5, "x1": 1.0, "y1": 2.0, "x2": 3.0, "y2": 4.0}
    ]
    same = compare(logged, [("P", "pothole", 0.5, 1.0, 2.0, 3.0, 4.0)])
    assert same["same_boxes"] and same["max_px_diff"] == 0.0
    moved = compare(logged, [("P", "pothole", 0.5, 1.5, 2.0, 3.0, 4.0)])
    assert moved["max_px_diff"] == pytest.approx(0.5)
    assert not compare(logged, [])["same_boxes"]
