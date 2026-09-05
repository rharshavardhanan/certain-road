"""Project a world-space pothole into an image-space `Detection`.

**Why this exists.** `driving/corridor.py` reasons in image space — a trapezoid in
the camera frame. The simulator reasons in world space — metres, top-down. Without
a projection between them the simulator could never run the real corridor code, and
would be an animation rather than a test harness.

**What it is not.** An idealised pinhole projection: no lens distortion, no
intrinsics, no calibration. Its job is to be monotone and plausible so that
"nearer" and "more central" mean what they should. It is a simulation aid and never
a substitute for calibrating the real camera.
"""

from __future__ import annotations

import math

from certain_road.artifacts.schema import Detection
from certain_road.sim.model import Camera, RobotState

# A ground point must be at least this far in front of the lens to be projected;
# closer than this the pinhole model diverges.
MIN_FORWARD_M = 0.05


def _image_v(forward_m: float, camera: Camera) -> float:
    """Image row for a ground point `forward_m` ahead. Larger v is lower in frame."""
    angle_below_horizontal = math.atan2(camera.height_m, forward_m)
    angle_from_axis = angle_below_horizontal - camera.pitch_rad
    half = camera.img_h / 2.0
    return half * (1.0 + math.tan(angle_from_axis) / math.tan(camera.vfov_rad / 2.0))


def _image_u(forward_m: float, lateral_m: float, camera: Camera) -> float:
    """Image column. `lateral_m` is positive to the left, which is smaller u."""
    angle_from_axis = math.atan2(lateral_m, forward_m)
    half = camera.img_w / 2.0
    return half * (1.0 - math.tan(angle_from_axis) / math.tan(camera.hfov_rad / 2.0))


def project_pothole(
    world_x: float,
    world_y: float,
    radius: float,
    state: RobotState,
    camera: Camera,
) -> Detection | None:
    """World-space pothole -> image-space `Detection`, or None if not visible.

    The box is built from the circle's four ground extremes rather than a fixed
    size, so it foreshortens with distance the way a real one does.
    """
    dx = world_x - state.x
    dy = world_y - state.y
    forward = dx * math.cos(state.heading) + dy * math.sin(state.heading)
    lateral = -dx * math.sin(state.heading) + dy * math.cos(state.heading)

    if forward <= MIN_FORWARD_M:
        return None  # behind the camera, or too close for the model to hold

    near = max(forward - radius, MIN_FORWARD_M)
    far = forward + radius

    y2 = _image_v(near, camera)  # near edge sits lower in the frame
    y1 = _image_v(far, camera)
    x1 = _image_u(forward, lateral + radius, camera)  # left edge
    x2 = _image_u(forward, lateral - radius, camera)

    # Entirely outside the frame in either axis: not visible.
    if x2 <= 0 or x1 >= camera.img_w or y2 <= 0 or y1 >= camera.img_h:
        return None

    return Detection(
        class_name="pothole",
        score=1.0,  # simulated ground truth; the detector's score is not modelled
        x1=max(0.0, x1),
        y1=max(0.0, y1),
        x2=min(float(camera.img_w), x2),
        y2=min(float(camera.img_h), y2),
        img_w=camera.img_w,
        img_h=camera.img_h,
    )
