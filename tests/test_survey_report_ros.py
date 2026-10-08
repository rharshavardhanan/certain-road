"""The ROS survey's core, without ROS: odometry, samples by distance, the ROI fixed on the road.

A straight synthetic drive at 5 m/s with 30 Hz frames, so frames never land exactly on a 5 m
mark; flat damage patches are projected into each frame with core.geometry. Every patch must
be counted exactly once, where it is, and scored by certain_road.survey.
"""

import math
import sys

import pytest
import yaml

from certain_road.core.geometry import project
from certain_road.core.paths import repo_root
from certain_road.dashboard.survey_report import CAPTION
from certain_road.survey import sample, scoring
from certain_road.survey.rsl import load_config as load_rsl

sys.path.insert(0, str(repo_root() / "ros" / "certain_road_survey"))

from certain_road_survey.core import Odometry, Pose, RosSurvey  # noqa: E402

ROOT = repo_root()
CFG = yaml.safe_load((ROOT / "configs/report/ros_survey.yaml").read_text())
PROJECT = yaml.safe_load((ROOT / "configs/project.yaml").read_text())
REPORT = yaml.safe_load((ROOT / "configs/report/survey_environments.yaml").read_text())
RSL = load_rsl(ROOT / REPORT["rsl_config"])
S = PROJECT["sim"]
W, H = S["cam_w"], S["cam_h"]
F = (W / 2) / math.tan(S["cam_fov_rad"] / 2)
CAM = scoring.Camera(f=F, cx=W / 2, cy=H / 2, cam_h=1.3, pitch=math.radians(10.0))
KW = {"f": CAM.f, "cx": CAM.cx, "cy": CAM.cy, "cam_h": CAM.cam_h, "pitch": CAM.pitch}
FWD = CFG["camera"]["forward_of_odom_m"]
SPEED, FPS = 5.0, 30.0
# (class, near edge along the road, lateral centre, depth, width): driving-lane patches
PATCHES = [
    ("pothole", 12.3, 0.2, 0.6, 0.6),
    ("alligator_crack", 21.0, -0.5, 1.5, 1.2),
    ("pothole", 27.95, 0.0, 0.5, 0.5),  # right at a strip boundary (mark 25 + 3)
    ("linear_crack", 40.4, 0.8, 1.0, 0.2),
    ("pothole", 66.1, -1.0, 0.8, 0.7),
    ("pothole", 30.0, 3.0, 0.6, 0.6),  # oncoming lane: never in the ROI
]


def box(cls, near, lat, depth, width, cam_x):
    pts = [
        project(near + a - cam_x, lat + b, **KW)
        for a in (0.0, depth)
        for b in (-width / 2, width / 2)
    ]
    us, vs = [p[0] for p in pts], [p[1] for p in pts]
    return (cls, 0.8, min(us), min(vs), max(us), max(vs))


def drive(survey: RosSurvey, until_m: float, gap: tuple[float, float] | None = None):
    survey.set_intrinsics(CAM.f, CAM.cx, CAM.cy)
    closed = []
    n = int(until_m / SPEED * FPS)
    for k in range(n):
        t = k / FPS
        base_x = SPEED * t - FWD  # the camera starts at chainage 0
        survey.pose(Pose(t, base_x, 0.0, 0.0))
        cam_x = base_x + FWD
        if gap and gap[0] <= cam_x < gap[1]:
            continue  # a perception stall: no frame
        dets = [
            box(c, near, lat, d, w, cam_x)
            for c, near, lat, d, w in PATCHES
            if 2.5 <= near - cam_x <= 12.0
        ]
        seg = survey.frame(t, None, dets)
        if seg:
            closed.append(seg)
    return closed


def new_survey(tmp_path, simulated=True) -> RosSurvey:
    return RosSurvey(
        CFG,
        PROJECT,
        RSL,
        REPORT,
        tmp_path,
        label="Synthetic road",
        simulated=simulated,
        run_dir_label="runs/ros_survey/test",
    )


def test_world_x_chainage_is_the_cameras_x_and_interpolates():
    odo = Odometry("world_x", 2.0, 10)
    assert odo.chainage_at(0.0) is None
    odo.add(Pose(1.0, 10.0, 0.0, 0.0))
    odo.add(Pose(2.0, 20.0, 0.0, 0.0))
    assert odo.chainage_at(1.0) == pytest.approx(12.0)
    assert odo.chainage_at(1.5) == pytest.approx(17.0)
    assert odo.chainage_at(5.0) == pytest.approx(22.0)  # newest pose after the history
    assert odo.chainage_at(0.5) is None
    odo.add(Pose(1.5, 99.0, 0.0, 0.0))  # out of order: ignored
    assert odo.chainage_at(1.5) == pytest.approx(17.0)


def test_path_chainage_follows_the_distance_travelled():
    odo = Odometry("path", 0.0, 10)
    for i, (x, y) in enumerate([(0, 0), (3, 4), (3, 10)]):
        odo.add(Pose(float(i), float(x), float(y), 0.0))
    assert odo.chainage_at(2.0) == pytest.approx(11.0)
    with pytest.raises(ValueError):
        Odometry("odometer", 0.0, 10)


def test_every_patch_is_counted_once_where_it_is(tmp_path):
    s = new_survey(tmp_path)
    drive(s, 80.0)
    counted = [d for smp in s.samples for d in smp["dets"]]
    lane = [p for p in PATCHES if abs(p[2]) <= PROJECT["scoring"]["lane_width_m"] / 2]
    assert len(counted) == len(lane)
    assert sorted(d[0] for d in counted) == sorted(p[0] for p in lane)
    for item in s.items:
        near = min(
            (p for p in lane if p[0] == item["cls"]),
            key=lambda p: abs(p[1] - item["location"]["chainage_m"]),
        )
        assert item["location"]["chainage_m"] == pytest.approx(near[1], abs=0.05)
        # the box's bottom centre is not the patch's centre line under perspective: a few cm
        assert item["location"]["lateral_m"] == pytest.approx(near[2], abs=0.1)
        assert item["false_alarm"] is None and item["model"] == (
            "P" if item["cls"] == "pothole" else "B"
        )
    marks = [smp["mark_m"] for smp in s.samples]
    assert marks == [5.0 * i for i in range(len(marks))]
    assert all(0 <= smp["chainage_m"] - smp["mark_m"] < SPEED / FPS + 1e-9 for smp in s.samples)


def test_segments_close_every_ten_samples_and_score_by_the_survey_code(tmp_path):
    s = new_survey(tmp_path)
    closed = drive(s, 120.0)
    per = round(PROJECT["scoring"]["segment_m"] / PROJECT["edge"]["sample_every_m"])
    assert len(closed) == len(s.samples) // per
    first = closed[0]
    boxes = [(d[0], *d[2:]) for smp in s.samples[:per] for d in smp["dets"]]
    expect = sample.score_boxes(
        boxes,
        CAM,
        segment_m=PROJECT["scoring"]["segment_m"],
        lane_width_m=PROJECT["scoring"]["lane_width_m"],
        weights=PROJECT["scoring"]["deduct_weights"],
    )
    assert first["vision_estimated_pci"] == pytest.approx(round(expect["pci"], 2))
    assert first["x0_m"] == pytest.approx(CFG["roi_near_m"])
    assert first["x1_m"] == pytest.approx(per * 5.0 + CFG["roi_near_m"])
    assert first["vision_estimated_pci"] < 100.0


def test_a_stall_skips_marks_and_says_so(tmp_path):
    s = new_survey(tmp_path)
    drive(s, 60.0, gap=(14.0, 26.0))
    assert s.skipped_marks == 2  # 15 and 20 passed without a frame; 25 was taken late
    assert 15.0 not in [smp["mark_m"] for smp in s.samples]


def test_the_report_is_written_and_says_there_is_no_ground_truth(tmp_path):
    s = new_survey(tmp_path, simulated=False)
    drive(s, 80.0)
    s.finish()
    path = s.write({"utc": "now", "commit": "test"})
    page = path.read_text()
    assert "Synthetic road" in page and CAPTION not in page
    assert "No ground truth here" in page
    assert "Simulated:" not in page and "re-rendered" not in page  # a real camera claims neither
    assert "saved live from the camera topic" in page
    assert (tmp_path / "survey.json").exists() and (tmp_path / "gallery.json").exists()
    sim = new_survey(tmp_path / "sim", simulated=True)
    drive(sim, 80.0)
    sim.finish()
    assert CAPTION in sim.write({"utc": "now", "commit": "test"}).read_text()
