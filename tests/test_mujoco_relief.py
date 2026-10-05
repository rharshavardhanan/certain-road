"""Look v2's 3D potholes: holes only where potholes are, under their outline, never above road.

Pure geometry: a synthetic texture catalogue, no GL and no data/ folder.
"""

import math

import mujoco
import numpy as np

from sim.mujoco.relief import depth_at, tile_mesh
from sim.mujoco.road import generate, load_config

FAKE = {
    "pothole": [("p1", 1.3, 0, 900, 700), ("p2", 1.1, 0, 800, 720)],
    "linear_crack": [("l1", 3.5, 2000, 3000, 860)],
    "alligator_crack": [("a1", 1.33, 2000, 2700, 2025)],
}
CFG = load_config("v2")
ROAD = generate("poor", 0, FAKE, CFG)
POTS = [i for i in ROAD.instances if i.cls == "pothole"]


def test_depth_reaches_the_drawn_depth_inside_and_is_zero_off_the_potholes():
    lo, hi = CFG["relief"]["depth_m"]
    rough = CFG["relief"]["floor_roughness"]
    for p in POTS:
        centre = depth_at(ROAD, CFG, np.array([p.x_m]), np.array([p.y_m]))[0]
        assert lo * (1 - rough / 2) * 0.9 <= centre <= hi * (1 + rough / 2)
        # just outside the ellipse along its own axis: road level, unless another pothole is there
        ca, sa = math.cos(p.angle_rad), math.sin(p.angle_rad)
        out = p.length_m / 2 * 1.3
        x, y = p.x_m + out * ca, p.y_m + out * sa
        others = [
            q
            for q in POTS
            if q is not p and q.bbox[0] <= x <= q.bbox[2] and q.bbox[1] <= y <= q.bbox[3]
        ]
        if not others:
            assert depth_at(ROAD, CFG, np.array([x]), np.array([y]))[0] == 0.0
    xs, ys = np.meshgrid(np.linspace(0, ROAD.length_m, 900), np.linspace(-3.5, 3.5, 25))
    d = depth_at(ROAD, CFG, xs, ys)
    assert d.min() >= 0.0 and d.max() <= hi * (1 + rough / 2)


def test_v1_has_no_relief():
    assert "relief" not in load_config("v1")


def test_tile_mesh_keeps_the_flat_quads_uvs_and_sinks_only_under_potholes():
    p = POTS[0]
    tm = CFG["surface"]["tile_m"]
    k = int(p.x_m // tm)
    x0, x1 = k * tm, (k + 1) * tm
    spec = mujoco.MjSpec()
    tile_mesh(spec, "t", ROAD, CFG, x0, x1, 3.5)
    mesh = spec.meshes[0]
    v = np.array(mesh.uservert).reshape(-1, 3)
    uv = np.array(mesh.usertexcoord).reshape(-1, 2)
    np.testing.assert_allclose(uv[:, 0], (v[:, 0] - x0) / tm, atol=1e-5)  # MuJoCo stores float32
    np.testing.assert_allclose(uv[:, 1], (v[:, 1] + 3.5) / 7.0, atol=1e-5)
    assert v[:, 2].max() == 0.0 and v[:, 2].min() < -0.02  # a hole, and nothing above road
    edge = np.isclose(np.abs(v[:, 1]), 3.5)
    assert np.all(v[edge, 2] == 0.0)  # the carriageway edge meets the kerbs at road level
    faces = np.array(mesh.userface).reshape(-1, 3)
    a, b, c = v[faces[:, 0]], v[faces[:, 1]], v[faces[:, 2]]
    nz = np.cross(b - a, c - a)[:, 2]
    assert np.all(nz > 0)  # every face points up, as the flat quad's did
