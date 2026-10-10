"""The mount maths recovers a known camera height, pitch and roll from a floor-lying board."""

import math
import sys

import cv2
import numpy as np
import pytest

from certain_road.core.paths import repo_root

sys.path.insert(0, str(repo_root() / "scripts"))

from calibrate_camera import CFG, board_points, mount_from_pose, nominal_k  # noqa: E402


def synthetic_pose(height: float, pitch: float, roll: float = 0.0):
    """World: the board's plane is z = 0, z up; the camera looks along +y, pitched down."""
    z_c = np.array([0.0, math.cos(pitch), -math.sin(pitch)])  # optical axis
    x_c = np.array([1.0, 0.0, 0.0])
    x_c = x_c * math.cos(roll) + np.cross(z_c, x_c) * math.sin(roll)  # roll about the axis
    y_c = np.cross(z_c, x_c)
    r_wc = np.column_stack([x_c, y_c, z_c])  # camera -> world
    reach = height / math.tan(pitch)  # where the axis meets the floor
    centre = np.array([0.1, -reach, height])  # board's corner region sits near the origin
    r = r_wc.T
    return cv2.Rodrigues(r)[0], -r @ centre


@pytest.mark.parametrize(
    ("height", "pitch_deg", "roll_deg"), [(0.22, 15, 0), (0.25, 25, 0), (0.20, 20, 3)]
)
def test_mount_recovers_height_pitch_and_roll(height, pitch_deg, roll_deg):
    k, dist = nominal_k(CFG)
    obj = board_points(CFG)
    rvec, tvec = synthetic_pose(height, math.radians(pitch_deg), math.radians(roll_deg))
    img, _ = cv2.projectPoints(obj, rvec, tvec, k, dist)
    ok, r2, t2 = cv2.solvePnP(obj, img.reshape(-1, 2), k, dist)
    assert ok
    m = mount_from_pose(r2, t2)
    assert m["height_m"] == pytest.approx(height, abs=1e-3)
    assert math.degrees(m["pitch_rad"]) == pytest.approx(pitch_deg, abs=0.1)
    assert math.degrees(m["roll_rad"]) == pytest.approx(roll_deg, abs=0.1)


def test_board_has_the_configured_size():
    nx, ny = CFG["board"]["inner_corners"]
    pts = board_points(CFG)
    assert len(pts) == nx * ny
    assert pts[:, :2].max(0) == pytest.approx(
        [(nx - 1), (ny - 1)] * np.array(CFG["board"]["square_m"])
    )
