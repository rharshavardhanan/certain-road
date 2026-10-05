"""The MuJoCo camera is the design camera, and it agrees with core.geometry's IPM.

The survey projects every detection to the ground with `core.geometry`. If the
simulator's camera differed from the one that IPM assumes, every footprint and every
vision-estimated PCI the demo shows would carry an error the real system does not have.
"""

import math

import mujoco
import numpy as np
import pytest

from certain_road.core.geometry import project
from sim.mujoco.scene import camera_quat, design_camera

CAM = design_camera()
CX, CY = CAM["w"] / 2, CAM["h"] / 2


def _scene(marker=None):
    spec = mujoco.MjSpec()
    spec.visual.global_.offwidth, spec.visual.global_.offheight = CAM["w"], CAM["h"]
    spec.worldbody.add_geom(
        type=mujoco.mjtGeom.mjGEOM_PLANE, size=[50, 50, 1], rgba=[0.2, 0.2, 0.2, 1]
    )
    if marker is not None:  # emissive, so the test reads position, not lighting
        spec.add_material(name="lit", emission=1.0, rgba=[1, 1, 1, 1])
        spec.worldbody.add_geom(
            type=mujoco.mjtGeom.mjGEOM_BOX,
            pos=[*marker, 0.001],
            size=[0.06, 0.06, 0.001],
            material="lit",
            contype=0,
            conaffinity=0,
        )
    veh = spec.worldbody.add_body(name="vehicle", mocap=True, pos=[0, 0, 0])
    veh.add_camera(
        name="cam", pos=[0, 0, CAM["height"]], quat=camera_quat(CAM["pitch"]), fovy=CAM["fovy_deg"]
    )
    model = spec.compile()
    data = mujoco.MjData(model)
    mujoco.mj_forward(model, data)
    return model, data


def _mujoco_pixel(model, data, world):
    p = data.cam_xmat[0].reshape(3, 3).T @ (np.array(world) - data.cam_xpos[0])
    f = (CAM["h"] / 2) / math.tan(math.radians(model.cam_fovy[0]) / 2)
    return CX + f * p[0] / -p[2], CY - f * p[1] / -p[2]


def test_fovy_gives_core_geometrys_focal_length():
    assert (CAM["h"] / 2) / math.tan(math.radians(CAM["fovy_deg"]) / 2) == pytest.approx(
        CAM["f"], rel=1e-12
    )


def test_camera_projection_matches_ipm():
    model, data = _scene()
    for fwd in (2.5, 5.0, 10.0, 20.0):
        for left in (-3.0, 0.0, 2.0):
            u, v = _mujoco_pixel(model, data, (fwd, left, 0.0))
            pu, pv = project(
                fwd, left, f=CAM["f"], cx=CX, cy=CY, cam_h=CAM["height"], pitch=CAM["pitch"]
            )
            assert (u, v) == pytest.approx((pu, pv), abs=1e-6)


def test_a_rendered_marker_lands_where_ipm_says():
    marker = (8.0, 1.0)
    model, data = _scene(marker)
    try:
        renderer = mujoco.Renderer(model, CAM["h"], CAM["w"])
    except Exception as exc:  # no OpenGL context (headless CI)
        pytest.skip(f"no GL context: {exc}")
    renderer.update_scene(data, camera="cam")
    img = renderer.render().mean(axis=2)
    vs, us = np.nonzero(img > 200)
    pu, pv = project(*marker, f=CAM["f"], cx=CX, cy=CY, cam_h=CAM["height"], pitch=CAM["pitch"])
    assert abs(us.mean() - pu) < 1.5 and abs(vs.mean() - pv) < 1.5
