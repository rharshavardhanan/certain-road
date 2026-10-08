"""Scoring a Gazebo drive: the projection agrees with the MuJoCo demo's, and the counts are right.

At the design pose (1.3 m, 10 deg down, in the driving lane) the per-frame ground-truth boxes
must be exactly the MuJoCo demo's (sim/mujoco/survey.gt_boxes_by_id). Off that pose they
follow the true camera. Pure geometry and bookkeeping: no Gazebo, no models.
"""

import math

import numpy as np
import pytest

from sim.gazebo import evaluate as ev
from sim.mujoco.road import generate, load_config
from sim.mujoco.scene import design_camera
from sim.mujoco.survey import gt_boxes_by_id

FAKE = {
    "pothole": [("p1", 1.3, 0, 900, 700), ("p2", 1.1, 0, 800, 720)],
    "linear_crack": [("l1", 3.5, 2000, 3000, 860)],
    "alligator_crack": [("a1", 1.33, 2000, 2700, 2025)],
}
LOOK = load_config("v2")
ROAD = generate("poor", 0, FAKE, LOOK)
CAM = design_camera()
K = np.array([[CAM["f"], 0, CAM["w"] / 2], [0, CAM["f"], CAM["h"] / 2], [0, 0, 1]])
N = LOOK["survey"]["gt_outline_points"]


def nominal(x):
    return ev.camera_world(
        [x, ROAD.drive_lane_y, CAM["height"]], [1, 0, 0, 0], [0, 0, 0], [0, CAM["pitch"], 0]
    )


@pytest.mark.parametrize("x", [30.0, 61.5, 120.0, 200.0])
def test_design_pose_reproduces_the_mujoco_demos_boxes(x):
    reach = 13.0
    mine = ev.gt_boxes(ROAD, *nominal(x), K, (CAM["w"], CAM["h"]), reach, N, 0.1)
    theirs = gt_boxes_by_id(ROAD, x, CAM, LOOK, max_m=reach)
    assert [g[0] for g in mine] == [i for i, _ in theirs]
    for g, (_, b) in zip(mine, theirs, strict=True):
        assert g[1] == b[0]
        np.testing.assert_allclose(g[2:], b[1:], atol=1e-6)


def test_a_body_pitched_nose_down_moves_the_boxes_up_the_frame():
    x = next(i.x_m for i in ROAD.instances if i.cls == "pothole") - 8
    t0, r0 = nominal(x)
    t1, r1 = ev.camera_world(
        [x, ROAD.drive_lane_y, CAM["height"]],
        [1, 0, 0, 0],
        [0, 0, 0],
        [0, CAM["pitch"] + math.radians(1.0), 0],
    )
    a = {g[0]: g for g in ev.gt_boxes(ROAD, t0, r0, K, (CAM["w"], CAM["h"]), 13, N, 0.1)}
    b = {g[0]: g for g in ev.gt_boxes(ROAD, t1, r1, K, (CAM["w"], CAM["h"]), 13, N, 0.1)}
    common = [i for i in a if i in b and a[i][3] > 0 and b[i][3] > 0]
    assert common and all(
        b[i][3] < a[i][3] for i in common
    )  # looking further down: higher in frame


def test_gate_row_is_the_mujoco_demos():
    from sim.mujoco.drive import gate_row

    assert ev.gate_row(K) == pytest.approx(gate_row(CAM))


def test_pose_interpolation_and_euler_round_trip():
    q = np.array([math.cos(0.1), 0, math.sin(0.1), 0])  # pitch 0.2 rad
    odom = np.array([[0.0, 0, 0, 0, 1, 0, 0, 0], [1.0, 2, 4, 0, *q]])
    p, qm = ev.interp_pose(odom, 0.5)
    np.testing.assert_allclose(p, [1, 2, 0])
    assert ev.euler(ev.quat_mat(qm))[1] == pytest.approx(0.1, abs=1e-3)
    r = ev.rpy_mat(0.1, -0.2, 0.3)
    np.testing.assert_allclose(ev.euler(r), [0.1, -0.2, 0.3])


def test_score_counts_in_view_any_frame_and_confirmed_hits():
    pots = [i for i in ROAD.instances if i.cls == "pothole"][:3]
    gate = 300.0
    box = [100.0, 400.0, 200.0, 450.0]
    recs = [
        {  # pothole 0 in view and boxed; pothole 1 in view, missed; pothole 2 above the gate
            "gt": [
                [pots[0].id, "pothole", *box],
                [pots[1].id, "pothole", 500, 400, 600, 450],
                [pots[2].id, "pothole", 0, 100, 50, 120],
            ],
            "raw": [{"model": "P", "cls": "pothole", "conf": 0.5, "box": box}],
            "tracked": [
                {
                    "model": "P",
                    "cls": "pothole",
                    "conf": 0.5,
                    "box": box,
                    "track": 1,
                    "confirmed": True,
                },
                {
                    "model": "P",
                    "cls": "pothole",
                    "conf": 0.4,
                    "box": [900, 600, 950, 650],
                    "track": 2,
                    "confirmed": True,
                },
            ],
        }
    ]
    s = ev.score(recs, ROAD, gate, 0.1, km=0.5)["pothole"]
    assert (s["in_view"], s["boxed_any_frame"], s["confirmed_hit"]) == (2, 1, 1)
    assert s["false_alarm_tracks"] == 1 and s["false_alarms_per_km"] == 2.0


def test_a_wheel_crossing_a_pothole_is_an_event():
    import yaml

    from certain_road.core.paths import repo_root

    gz = yaml.safe_load((repo_root() / "configs/sim/gazebo.yaml").read_text())
    p = next(i for i in ROAD.instances if i.cls == "pothole")
    veh = gz["vehicle"]
    y_body = p.y_m - veh["track_m"] / 2  # the left wheels run through the pothole's centre
    t = np.arange(0, 20, 0.01)
    x = p.x_m - 30 + 5.0 * t
    odom = np.zeros((len(t), 9))  # t, x, y, z, qw, qx, qy, qz, speed
    odom[:, 0], odom[:, 1], odom[:, 2] = t, x, y_body
    odom[:, 3], odom[:, 4], odom[:, 8] = veh["cg_height_m"], 1.0, 5.0 / 0.9
    odom[:, 3] -= 0.01 * np.exp(-(((x - p.x_m) / 0.5) ** 2))  # a 10 mm dip as the wheels pass
    legs = ("front_left", "front_right", "rear_left", "rear_right")
    joints = [{"t": float(s), **{f"{w}_suspension": 0.0 for w in legs}} for s in t]
    r = ev.ride_events(odom, joints, ROAD, LOOK, gz)
    assert r["control_samples"] > 0 and r["control"]["heave_mm"]["max"] < 1.0  # plain road: flat
    left = [
        e
        for e in r["list"]
        if e["wheel"] in ("front_left", "rear_left") and abs(e["x_m"] - p.x_m) < p.length_m
    ]
    assert left and max(e["heave_mm"] for e in left) == pytest.approx(10.0, abs=1.0)
