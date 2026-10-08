"""The rendered camera frame agrees with the projection the driving code judges.

If these drift apart, the ROS demo would show one pothole while the planner reasoned
about another (D093).
"""

import numpy as np
import pytest

from certain_road.core.paths import repo_root
from certain_road.sim.camera_image import ground_points, load_palette, render_frame
from certain_road.sim.model import RobotState, load_robot
from certain_road.sim.project import project_pothole
from certain_road.sim.scenario import SCENARIOS, Pothole

ROBOT = load_robot(repo_root() / "configs" / "sim" / "robot.yaml")
CAMERA = ROBOT.camera
PALETTE = load_palette(repo_root() / "configs" / "sim" / "camera_image.yaml")
ORIGIN = RobotState(0.0, 0.0, 0.0, 0.0)


def pothole_mask(img: np.ndarray) -> np.ndarray:
    return np.all(img == PALETTE.pothole_rgb, axis=-1) | np.all(
        img == PALETTE.pothole_rim_rgb, axis=-1
    )


def test_frame_shape_and_type():
    img = render_frame(ORIGIN, [], CAMERA, PALETTE)
    assert img.shape == (CAMERA.img_h, CAMERA.img_w, 3)
    assert img.dtype == np.uint8


def test_top_row_is_sky_and_bottom_row_is_road():
    img = render_frame(ORIGIN, [], CAMERA, PALETTE)
    assert np.all(img[0] == PALETTE.sky_rgb)
    lo = np.asarray(PALETTE.asphalt_rgb) - PALETTE.asphalt_noise
    hi = np.asarray(PALETTE.asphalt_rgb) + PALETTE.asphalt_noise
    assert np.all((img[-1] >= lo) & (img[-1] <= hi))


def test_asphalt_never_takes_a_pothole_colour():
    """pothole_mask reads potholes off colour alone; the config must keep that true."""
    img = render_frame(ORIGIN, [], CAMERA, PALETTE)
    assert not pothole_mask(img).any()


@pytest.mark.parametrize(
    ("pothole", "state"),
    [
        (Pothole(1.0, 0.0), ORIGIN),
        (Pothole(1.5, 0.18), ORIGIN),
        (Pothole(0.8, -0.1, 0.1), ORIGIN),
        (Pothole(1.6, 0.1), RobotState(0.3, -0.05, 0.2, 0.0)),
    ],
)
def test_rendered_pothole_fills_its_projected_box(pothole, state):
    det = project_pothole(pothole.x, pothole.y, pothole.radius, state, CAMERA)
    assert det is not None
    mask = pothole_mask(render_frame(state, [pothole], CAMERA, PALETTE))
    rows, cols = np.nonzero(mask)
    assert rows.size > 0

    # Rows: the near and far edges, which proximity and urgency read, agree to a pixel.
    assert abs(rows.min() - det.y1) <= 1.0
    assert abs(rows.max() + 1 - det.y2) <= 1.0

    # Columns: project_pothole takes the width at the disc's centre distance, which
    # under-reports it as the disc nears the lens (measured: 1-2 % at the ~0.9 m decision
    # distance, 7 % at 0.5 m). The render is the true disc; at these distances, >= 0.8 m,
    # the two agree to 2.5 % of the box width plus a pixel. D093.
    slack = 0.025 * (det.x2 - det.x1) + 1.0
    assert cols.min() >= det.x1 - slack
    assert cols.max() + 1 <= det.x2 + slack
    assert (cols.max() + 1 - cols.min()) >= det.x2 - det.x1 - 1.0


def test_pothole_behind_the_robot_is_not_drawn():
    img = render_frame(ORIGIN, [Pothole(-1.0, 0.0)], CAMERA, PALETTE)
    assert not pothole_mask(img).any()


def test_rendering_is_deterministic():
    scenario = SCENARIOS["multiple"]
    a = render_frame(ORIGIN, scenario.potholes, CAMERA, PALETTE)
    b = render_frame(ORIGIN, scenario.potholes, CAMERA, PALETTE)
    assert np.array_equal(a, b)


def test_texture_is_fixed_to_the_ground():
    """Driving forward by one texture cell must change the frame: motion is visible."""
    a = render_frame(ORIGIN, [], CAMERA, PALETTE)
    moved = RobotState(PALETTE.asphalt_texture_m * 3, 0.0, 0.0, 0.0)
    b = render_frame(moved, [], CAMERA, PALETTE)
    assert not np.array_equal(a, b)


def test_cached_ground_points_are_read_only():
    _, forward, _ = ground_points(CAMERA)
    with pytest.raises(ValueError):
        forward[0, 0] = 1.0
