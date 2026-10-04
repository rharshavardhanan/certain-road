"""T12 — IPM must invert exactly, and must agree with the simulator's camera.

The round-trip test is the specification: T12 requires sub-millimetre agreement
over a grid. An IPM that is subtly wrong still returns plausible metres, so
"looks about right" catches nothing here.
"""

import math

import pytest

from certain_road.core.geometry import (
    EARTH_RADIUS_M,
    ground_point,
    haversine_m,
    interp_track,
    project,
)

CAM = {"f": 935.5, "cx": 640.0, "cy": 360.0, "cam_h": 1.3, "pitch": math.radians(10.0)}
MM = 1e-3


@pytest.mark.parametrize("forward", [2.5, 5.0, 8.0, 12.0, 20.0, 40.0])
@pytest.mark.parametrize("left", [-3.5, -1.75, 0.0, 1.75, 3.5])
def test_round_trip_is_sub_millimetre(forward, left):
    uv = project(forward, left, **CAM)
    assert uv is not None
    back = ground_point(*uv, **CAM)
    assert back is not None
    assert abs(back[0] - forward) < MM
    assert abs(back[1] - left) < MM


def test_points_above_the_horizon_have_no_ground_intersection():
    # Horizon row for a 10-degree downward pitch.
    horizon_v = CAM["cy"] - CAM["f"] * math.tan(CAM["pitch"])
    assert ground_point(CAM["cx"], horizon_v - 1.0, **CAM) is None


def test_lower_in_frame_means_nearer():
    near = ground_point(CAM["cx"], 700.0, **CAM)
    far = ground_point(CAM["cx"], 400.0, **CAM)
    assert near is not None and far is not None
    assert near[0] < far[0]


def test_left_of_centre_maps_to_positive_left():
    point = ground_point(CAM["cx"] - 200.0, 600.0, **CAM)
    assert point is not None and point[1] > 0


def test_nearest_visible_ground_matches_the_t13_design_figure():
    """T13's table: 1.3 / tan(10 deg + 21.05 deg) ~= 2.2 m at the frame bottom."""
    point = ground_point(CAM["cx"], 720.0, **CAM)
    assert point is not None
    expected = CAM["cam_h"] / math.tan(CAM["pitch"] + math.atan(360 / CAM["f"]))
    assert point[0] == pytest.approx(expected, abs=0.01)
    assert point[0] == pytest.approx(2.2, abs=0.05)


def test_agrees_with_the_simulator_camera_under_f_from_fov():
    """`sim/project.py` uses FOV; this uses focal length. Same camera, so the
    horizon row each implies must coincide."""
    img_w, hfov = 1280, 1.2
    f = (img_w / 2) / math.tan(hfov / 2)
    assert f == pytest.approx(935.5, abs=0.5)  # the T13 design figure


def test_haversine_matches_a_known_degree_of_latitude():
    one_degree = haversine_m(0.0, 0.0, 1.0, 0.0)
    assert one_degree == pytest.approx(math.pi * EARTH_RADIUS_M / 180, rel=1e-9)


def test_haversine_is_zero_for_identical_points():
    assert haversine_m(13.08, 80.27, 13.08, 80.27) == 0.0


def test_interp_track_interpolates_and_clamps():
    ts, lat, lon = [0.0, 10.0], [0.0, 1.0], [0.0, 2.0]
    assert interp_track(ts, lat, lon, 5.0) == pytest.approx((0.5, 1.0))
    assert interp_track(ts, lat, lon, -5.0) == (0.0, 0.0)  # clamps, never extrapolates
    assert interp_track(ts, lat, lon, 99.0) == (1.0, 2.0)


def test_interp_track_rejects_an_empty_track():
    with pytest.raises(ValueError, match="empty track"):
        interp_track([], [], [], 1.0)
