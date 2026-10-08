"""The Gazebo export's pure half: meshes, the MuJoCo-to-Gazebo conversion, the world SDF.

A small MuJoCo scene stands in for the demo's: one road tile sunk under its potholes by
sim/mujoco/relief.py (a synthetic texture catalogue, as test_mujoco_relief.py uses), a
textured ground plane, and primitives in two colours. No Gazebo, no data/ folder.
"""

import math
import xml.etree.ElementTree as ET

import mujoco
import numpy as np
import pytest
import yaml

from certain_road.core.paths import repo_root
from sim.gazebo import meshes
from sim.gazebo.convert import convert
from sim.gazebo.export import floor_z, write_world
from sim.gazebo.world import rpy
from sim.mujoco.relief import tile_mesh
from sim.mujoco.road import generate, load_config

FAKE = {
    "pothole": [("p1", 1.3, 0, 900, 700), ("p2", 1.1, 0, 800, 720)],
    "linear_crack": [("l1", 3.5, 2000, 3000, 860)],
    "alligator_crack": [("a1", 1.33, 2000, 2700, 2025)],
}
LOOK = load_config("v2")
ROAD = generate("poor", 0, FAKE, LOOK)
GZ = yaml.safe_load((repo_root() / "configs/sim/gazebo.yaml").read_text())
TM = LOOK["surface"]["tile_m"]
POT = next(i for i in ROAD.instances if i.cls == "pothole")
K = int(POT.x_m // TM)
X0, X1 = K * TM, (K + 1) * TM
TEX = np.random.default_rng(0).integers(0, 255, (6, 10, 3), dtype=np.uint8)


def scene():
    """(compiled model, the tile's vertices as relief wrote them)."""
    spec = mujoco.MjSpec()
    t = spec.add_texture(
        name="road0", type=mujoco.mjtTexture.mjTEXTURE_2D, width=10, height=6, nchannel=3
    )
    t.data = TEX.tobytes()
    spec.add_material(name="road0").textures[mujoco.mjtTextureRole.mjTEXROLE_RGB] = "road0"
    g = spec.add_texture(
        name="ground", type=mujoco.mjtTexture.mjTEXTURE_2D, width=10, height=6, nchannel=3
    )
    g.data = TEX.tobytes()
    gm = spec.add_material(name="ground", texrepeat=[60, 60])
    gm.textures[mujoco.mjtTextureRole.mjTEXROLE_RGB] = "ground"
    tile_mesh(spec, "q0", ROAD, LOOK, X0, X1, 3.5)
    authored = np.array(spec.meshes[0].uservert).reshape(-1, 3)
    wb = spec.worldbody
    wb.add_geom(
        type=mujoco.mjtGeom.mjGEOM_MESH, meshname="q0", material="road0", contype=0, conaffinity=0
    )
    wb.add_geom(
        type=mujoco.mjtGeom.mjGEOM_PLANE,
        pos=[50, 0, -0.15],
        size=[100, 50, 1],
        material="ground",
        contype=0,
        conaffinity=0,
    )
    for i in range(3):  # white kerb stripes, near-identical shades: one merged mesh
        wb.add_geom(
            type=mujoco.mjtGeom.mjGEOM_BOX,
            pos=[i, 3.6, 0.075],
            size=[0.5, 0.125, 0.075],
            rgba=[0.86 + 0.01 * i, 0.86, 0.83, 1],
            contype=0,
            conaffinity=0,
        )
    wb.add_geom(
        type=mujoco.mjtGeom.mjGEOM_CYLINDER,
        pos=[5, 5, 4],
        size=[0.13, 4],
        rgba=[0.62, 0.61, 0.58, 1],
        contype=0,
        conaffinity=0,
    )
    wb.add_geom(
        type=mujoco.mjtGeom.mjGEOM_ELLIPSOID,
        pos=[7, 5, 6],
        size=[1, 0.8, 0.6],
        rgba=[0.62, 0.61, 0.58, 1],
        contype=0,
        conaffinity=0,
    )
    return spec.compile(), authored


MODEL, AUTHORED = scene()
TEXTURED, COLOURED = convert(MODEL, GZ["export"])


def world_vertices(part):
    rot = np.zeros(9)
    mujoco.mju_quat2Mat(rot, part.quat)
    return part.mesh.v @ rot.reshape(3, 3).T + part.pos


def outward(mesh):
    a, b, c = (mesh.v[mesh.f[:, k]] for k in range(3))
    n = np.cross(b - a, c - a)
    centre = (a + b + c) / 3
    return n, centre


@pytest.mark.parametrize(
    "mesh",
    [
        meshes.box(np.array([1.0, 2.0, 0.5])),
        meshes.cylinder(0.3, 1.0, 16),
        meshes.ellipsoid(np.array([1.0, 0.7, 0.5]), 12, 8),
    ],
)
def test_primitives_face_outward_and_their_normals_agree(mesh):
    n, centre = outward(mesh)
    assert np.all(np.einsum("ij,ij->i", n, centre) > 0)  # convex, centred: outward = away
    stored = mesh.vn[mesh.fn].mean(1)
    assert np.all(np.einsum("ij,ij->i", n, stored) > 0)


def test_obj_round_trips_and_flips_v_to_objs_convention(tmp_path):
    m = meshes.quad(0.0, 4.0, -1.0, 1.0, 0.0)
    meshes.write_obj(tmp_path / "q.obj", m, 4)
    text = (tmp_path / "q.obj").read_text()
    # MuJoCo v = 0 is the texture's first row; OBJ writes it as v = 1 (its top)
    assert "vt 0.000000 1.000000" in text
    back = meshes.read_obj(tmp_path / "q.obj")
    np.testing.assert_allclose(back.v, m.v)
    np.testing.assert_allclose(back.vt, m.vt)
    np.testing.assert_array_equal(back.f, m.f)


def test_merge_offsets_indices():
    a, b = meshes.box(np.ones(3)), meshes.box(np.ones(3)).transformed([10, 0, 0], np.eye(3))
    m = meshes.merge([a, b])
    assert len(m.v) == 2 * len(a.v) and m.f.max() == len(m.v) - 1
    assert m.v[m.f[len(a.f) :]][..., 0].min() == pytest.approx(9.0)


def test_road_tile_lands_where_relief_built_it_with_its_uvs_and_texture():
    tile = next(p for p in TEXTURED if p.name == "q0")
    v = world_vertices(tile)
    # every authored vertex survives MuJoCo's recentring, in the same place (float32)
    d = np.abs(v[:, None, :] - AUTHORED[None, :, :]).max(-1).min(0)
    assert d.max() < 1e-4
    assert v[:, 2].max() == pytest.approx(0.0, abs=1e-5) and v[:, 2].min() < -0.02
    # each corner's texture coordinate is the flat quad's: u along x, v across from y = -3.5
    corners = v[tile.mesh.f].reshape(-1, 3)
    uv = tile.mesh.vt[tile.mesh.ft].reshape(-1, 2)
    np.testing.assert_allclose(uv[:, 0], (corners[:, 0] - X0) / TM, atol=2e-5)
    np.testing.assert_allclose(uv[:, 1], (corners[:, 1] + 3.5) / 7.0, atol=2e-5)
    np.testing.assert_array_equal(tile.texture, TEX)
    assert tile.collide


def test_ground_plane_is_a_textured_quad_repeated_as_mujoco_repeats_it():
    ground = next(p for p in TEXTURED if p.name == "ground")
    assert not ground.collide
    v = world_vertices(ground)
    np.testing.assert_allclose(v[:, 2], -0.15, atol=1e-6)
    assert v[:, 0].min() == pytest.approx(-50) and v[:, 0].max() == pytest.approx(150)
    assert ground.mesh.vt.max() == pytest.approx(60)


def test_primitives_merge_by_colour_in_world_coordinates():
    counts = sorted(p.count for p in COLOURED)
    assert counts == [2, 3]  # kerb stripes; the pole and the blob share a grey
    kerb = next(p for p in COLOURED if p.count == 3)
    assert kerb.mesh.v[:, 1].min() == pytest.approx(3.475) and kerb.mesh.v[
        :, 0
    ].max() == pytest.approx(2.5)
    assert kerb.mesh.vt is None


def test_world_sdf_uses_only_relative_paths_and_collides_with_the_road(tmp_path):
    box = {"length_m": ROAD.length_m, "half_width_m": 3.5, "floor_z": floor_z(TEXTURED)}
    assert box["floor_z"] == pytest.approx(-0.15, abs=1e-6)
    stats = write_world(tmp_path, TEXTURED, COLOURED, LOOK, GZ, box)
    root = ET.parse(tmp_path / "world.sdf").getroot()
    uris = [e.text for e in root.iter("uri")] + [e.text for e in root.iter("albedo_map")]
    assert uris and all(not u.startswith(("/", "~")) and ".." not in u for u in uris)
    assert all((tmp_path / u).is_file() for u in uris)
    cols = {c.get("name") for c in root.iter("collision")}
    assert "q0_collision" in cols and "ground_collision" not in cols
    assert {"kerb_left", "kerb_right", "catch_plane"} <= cols
    names = [e.get("name") for e in root.iter() if e.get("name")]
    assert len(names) == len(set(names))  # SDF rejects sibling name clashes
    d = np.array(root.find(".//light/direction").text.split(), float)
    assert np.linalg.norm(d) == pytest.approx(1.0, abs=1e-5)
    assert stats["collision_meshes"] == 1 and stats["textures"] == 2


def test_rpy_inverts_a_known_rotation():
    q = np.zeros(4)
    mujoco.mju_euler2Quat(q, np.array([0.1, -0.2, 0.3]), "XYZ")
    r = np.zeros(9)
    mujoco.mju_quat2Mat(r, q)
    roll, pitch, yaw = rpy(q)
    cr, sr, cp, sp, cy, sy = (f(a) for a in (roll, pitch, yaw) for f in (math.cos, math.sin))
    rx = np.array([[1, 0, 0], [0, cr, -sr], [0, sr, cr]])
    ry = np.array([[cp, 0, sp], [0, 1, 0], [-sp, 0, cp]])
    rz = np.array([[cy, -sy, 0], [sy, cy, 0], [0, 0, 1]])
    np.testing.assert_allclose(rz @ ry @ rx, r.reshape(3, 3), atol=1e-9)


def test_parts_json_rebuilds_the_same_world_and_props_are_linearised(tmp_path):
    import json

    from sim.gazebo.world import world_sdf

    box = {"length_m": ROAD.length_m, "half_width_m": 3.5, "floor_z": floor_z(TEXTURED)}
    write_world(tmp_path, TEXTURED, COLOURED, LOOK, GZ, box)
    saved = json.loads((tmp_path / "parts.json").read_text())
    again = world_sdf(saved["parts"], LOOK, GZ, saved["road_box"])
    assert again == (tmp_path / "world.sdf").read_text()
    root = ET.fromstring(again)
    kerb = next(p for p in COLOURED if p.count == 3)
    vis = next(v for v in root.iter("visual") if v.get("name") == kerb.name)
    diffuse = np.array(vis.find("material/diffuse").text.split(), float)
    np.testing.assert_allclose(
        diffuse[:3], np.array(kerb.rgba[:3]) ** GZ["render"]["colour_gamma"], atol=1e-6
    )
    assert float(root.find(".//light/intensity").text) > 1.0  # SDF colours cap at 1
