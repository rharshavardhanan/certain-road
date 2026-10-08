"""Turn a compiled MuJoCo scene into Gazebo parts, geom by geom.

The Gazebo world is not a second road generator. `sim/mujoco/scene.build` builds the demo's
scene (road tiles baked from the photo textures and sunk under each pothole, kerbs,
shoulders, ground, poles, wall, signs, trees), and this module reads the compiled model back:

- **Textured geoms** (the road tiles, shoulders and ground) become one mesh each, kept in the
  geom's own frame, with the material's texture pixels as MuJoCo holds them. Meshes whose
  name matches `export.collide_mesh_pattern` (the road tiles) are also collision geometry, so
  each pothole is a real depression a wheel drops into, exactly under its texture.
- **Plain-colour primitives** (boxes, cylinders, ellipsoids, spheres) are tessellated and
  merged, one mesh per colour (`export.colour_step`), so a thousand kerb stripes and tree
  blobs cost Gazebo a few dozen visuals instead of a thousand entities.

What it does not carry over: MuJoCo's fog (Gazebo's Ogre 2 renderer has none), the sky's
gradient texture (a plain background colour stands in), and primitives' textures (the wall's
noise becomes its mean colour). Nothing here changes where anything is.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

import mujoco
import numpy as np

from sim.gazebo import meshes
from sim.gazebo.meshes import Mesh

RGB_ROLE = int(mujoco.mjtTextureRole.mjTEXROLE_RGB)
# plain ints: a numpy geom type and a pybind enum do not compare inside `in`
MESH, PLANE = int(mujoco.mjtGeom.mjGEOM_MESH), int(mujoco.mjtGeom.mjGEOM_PLANE)
BOX, CYLINDER = int(mujoco.mjtGeom.mjGEOM_BOX), int(mujoco.mjtGeom.mjGEOM_CYLINDER)
ELLIPSOID, SPHERE = int(mujoco.mjtGeom.mjGEOM_ELLIPSOID), int(mujoco.mjtGeom.mjGEOM_SPHERE)


@dataclass
class TexturedPart:
    """One textured MuJoCo geom: its mesh in its own frame, placed by pos and quat."""

    name: str  # mesh file stem
    material: str  # texture file stem
    mesh: Mesh
    pos: np.ndarray
    quat: np.ndarray  # w, x, y, z
    rgba: tuple[float, float, float, float]
    texture: np.ndarray | None  # H x W x 3 uint8 RGB; row 0 is texture v = 0
    collide: bool


@dataclass
class ColourPart:
    """Every primitive of one colour, merged, in world coordinates."""

    name: str
    mesh: Mesh
    rgba: tuple[float, float, float, float]
    count: int  # how many MuJoCo geoms it holds


def texture_rgb(model: mujoco.MjModel, texid: int) -> np.ndarray:
    """A 2D texture's pixels as MuJoCo stores them: row 0 maps to texture v = 0."""
    w, h, c = (int(a[texid]) for a in (model.tex_width, model.tex_height, model.tex_nchannel))
    adr = int(model.tex_adr[texid])
    return model.tex_data[adr : adr + w * h * c].reshape(h, w, c)[..., :3].copy()


def mesh_of(model: mujoco.MjModel, mid: int) -> Mesh:
    """Mesh `mid` in its own (compiled, recentred) frame, with its normals and UVs."""
    va, nv = model.mesh_vertadr[mid], model.mesh_vertnum[mid]
    fa, nf = model.mesh_faceadr[mid], model.mesh_facenum[mid]
    na, nn = model.mesh_normaladr[mid], model.mesh_normalnum[mid]
    ta, nt = model.mesh_texcoordadr[mid], model.mesh_texcoordnum[mid]
    textured = ta >= 0 and nt > 0
    return Mesh(
        model.mesh_vert[va : va + nv].astype(float),
        model.mesh_face[fa : fa + nf].copy(),
        model.mesh_normal[na : na + nn].astype(float),
        model.mesh_facenormal[fa : fa + nf].copy(),
        model.mesh_texcoord[ta : ta + nt].astype(float) if textured else None,
        model.mesh_facetexcoord[fa : fa + nf].copy() if textured else None,
    )


def _primitive(model: mujoco.MjModel, g: int, ex: dict) -> Mesh:
    t, size = int(model.geom_type[g]), model.geom_size[g]
    if t == BOX:
        return meshes.box(size)
    if t == CYLINDER:
        return meshes.cylinder(size[0], size[1], ex["cylinder_segments"])
    if t == ELLIPSOID:
        return meshes.ellipsoid(size, *ex["ellipsoid_segments"])
    if t == SPHERE:
        return meshes.ellipsoid(np.full(3, size[0]), *ex["ellipsoid_segments"])
    raise ValueError(f"geom {g}: MuJoCo geom type {mujoco.mjtGeom(t).name} has no conversion")


def _colour(model: mujoco.MjModel, g: int) -> np.ndarray:
    """What colour a primitive draws in: its rgba, or its material's times the texture mean."""
    mat = model.geom_matid[g]
    if mat < 0:
        return model.geom_rgba[g].astype(float)
    rgba = model.mat_rgba[mat].astype(float)
    tex = model.mat_texid[mat, RGB_ROLE]
    if tex >= 0:
        rgba[:3] *= texture_rgb(model, tex).reshape(-1, 3).mean(0) / 255.0
    return rgba


def convert(model: mujoco.MjModel, ex: dict) -> tuple[list[TexturedPart], list[ColourPart]]:
    """Every world geom of `model` as Gazebo parts. `ex` is gazebo.yaml's `export:` block."""
    data = mujoco.MjData(model)
    mujoco.mj_kinematics(model, data)
    collide = re.compile(ex["collide_mesh_pattern"])
    textured: list[TexturedPart] = []
    groups: dict[tuple, list[Mesh]] = {}
    colours: dict[tuple, list[np.ndarray]] = {}
    step = ex["colour_step"]
    for g in range(model.ngeom):
        t = int(model.geom_type[g])
        mat = model.geom_matid[g]
        tex = model.mat_texid[mat, RGB_ROLE] if mat >= 0 else -1
        quat = np.zeros(4)
        mujoco.mju_mat2Quat(quat, data.geom_xmat[g])
        if t in (MESH, PLANE) and tex >= 0:
            if t == MESH:
                mid = model.geom_dataid[g]
                name = mujoco.mj_id2name(model, mujoco.mjtObj.mjOBJ_MESH, mid)
                mesh = mesh_of(model, mid)
            else:  # a plane: a quad of its half-extents, its texture repeated per object
                sx, sy = model.geom_size[g][:2]
                name = mujoco.mj_id2name(model, mujoco.mjtObj.mjOBJ_MATERIAL, mat)
                mesh = meshes.quad(-sx, sx, -sy, sy, 0.0, tuple(model.mat_texrepeat[mat]))
            textured.append(
                TexturedPart(
                    name=name,
                    material=mujoco.mj_id2name(model, mujoco.mjtObj.mjOBJ_MATERIAL, mat),
                    mesh=mesh,
                    pos=data.geom_xpos[g].copy(),
                    quat=quat,
                    rgba=tuple(float(c) for c in model.mat_rgba[mat]),
                    texture=texture_rgb(model, tex),
                    collide=bool(collide.match(name)),
                )
            )
            continue
        rgba = _colour(model, g)
        key = tuple(np.round(rgba / step).astype(int))
        groups.setdefault(key, []).append(
            _primitive(model, g, ex).transformed(data.geom_xpos[g], data.geom_xmat[g])
        )
        colours.setdefault(key, []).append(rgba)
    coloured = [
        ColourPart(
            name=f"props_{k:02d}",
            mesh=meshes.merge(parts),
            rgba=tuple(float(c) for c in np.mean(colours[key], axis=0)),
            count=len(parts),
        )
        for k, (key, parts) in enumerate(sorted(groups.items()))
    ]
    return textured, coloured
