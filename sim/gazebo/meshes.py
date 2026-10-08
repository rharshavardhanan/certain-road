"""Triangle meshes for Gazebo: tessellated primitives, merging, and an OBJ writer.

Gazebo draws geometry from mesh files, and has no per-vertex colour, so every primitive the
MuJoCo scene places (kerb stripes, poles, tree canopy blobs) becomes triangles here and is
merged with the others of its colour. This module is pure numpy; it knows nothing of MuJoCo
or SDF.

**The v flip.** MuJoCo maps texture coordinate v = 0 to a texture's first row. OBJ puts
v = 0 at the image's bottom row, and Gazebo's OBJ loader flips it back. `write_obj` takes
MuJoCo's convention and writes OBJ's, so a texture saved row for row lands where MuJoCo
drew it.
"""

from __future__ import annotations

import io
import math
from dataclasses import dataclass
from pathlib import Path

import numpy as np


@dataclass
class Mesh:
    """OBJ-style mesh: separate position, texture and normal indices per face corner."""

    v: np.ndarray  # (n, 3) positions
    f: np.ndarray  # (m, 3) indices into v, counter-clockwise seen from outside
    vn: np.ndarray  # (k, 3) unit normals
    fn: np.ndarray  # (m, 3) indices into vn
    vt: np.ndarray | None = None  # (j, 2) texture coordinates, MuJoCo's v convention
    ft: np.ndarray | None = None  # (m, 3) indices into vt

    def transformed(self, pos, rot) -> Mesh:
        """This mesh moved by rotation `rot` (3x3) then translation `pos`."""
        r = np.asarray(rot, float).reshape(3, 3)
        return Mesh(
            self.v @ r.T + np.asarray(pos, float),
            self.f,
            self.vn @ r.T,
            self.fn,
            self.vt,
            self.ft,
        )


def merge(meshes: list[Mesh]) -> Mesh:
    """One mesh holding all of `meshes`; texture coordinates only if every part has them."""
    textured = all(m.vt is not None for m in meshes)
    v, f, vn, fn, vt, ft = [], [], [], [], [], []
    nv = nn = nt = 0
    for m in meshes:
        v.append(m.v)
        f.append(m.f + nv)
        vn.append(m.vn)
        fn.append(m.fn + nn)
        nv, nn = nv + len(m.v), nn + len(m.vn)
        if textured:
            vt.append(m.vt)
            ft.append(m.ft + nt)
            nt += len(m.vt)
    return Mesh(
        np.concatenate(v),
        np.concatenate(f),
        np.concatenate(vn),
        np.concatenate(fn),
        np.concatenate(vt) if textured else None,
        np.concatenate(ft) if textured else None,
    )


def box(half: np.ndarray) -> Mesh:
    """An axis-aligned box of half-extents `half`, centred on the origin, flat-shaded."""
    hx, hy, hz = (float(h) for h in half)
    v, f, vn = [], [], []
    for axis in range(3):
        for sign in (-1.0, 1.0):
            n = np.zeros(3)
            n[axis] = sign
            u, w = (axis + 1) % 3, (axis + 2) % 3  # cyclic, so u x w points along +axis
            if sign < 0:
                u, w = w, u  # keep the corners counter-clockwise seen from outside
            corners = []
            for a, b in ((-1, -1), (1, -1), (1, 1), (-1, 1)):
                p = np.zeros(3)
                p[axis] = sign
                p[u], p[w] = a, b
                corners.append(p * [hx, hy, hz])
            base = len(v)
            v += corners
            f += [[base, base + 1, base + 2], [base, base + 2, base + 3]]
            vn.append(n)
    f = np.array(f)
    fn = np.repeat(np.arange(6), 2)[:, None].repeat(3, 1)
    return Mesh(np.array(v), f, np.array(vn), fn)


def cylinder(radius: float, half_height: float, segments: int) -> Mesh:
    """A capped cylinder along z, centred on the origin; smooth side, flat caps."""
    t = np.linspace(0, 2 * math.pi, segments, endpoint=False)
    ring = np.stack([np.cos(t), np.sin(t), np.zeros_like(t)], 1)
    lo = ring * [radius, radius, 0] + [0, 0, -half_height]
    hi = ring * [radius, radius, 0] + [0, 0, half_height]
    v = np.concatenate([lo, hi, [[0, 0, -half_height], [0, 0, half_height]]])
    n = segments
    i = np.arange(n)
    j = (i + 1) % n
    side = np.concatenate([np.stack([i, j, j + n], 1), np.stack([i, j + n, i + n], 1)])
    bottom = np.stack([np.full(n, 2 * n), j, i], 1)
    top = np.stack([np.full(n, 2 * n + 1), i + n, j + n], 1)
    f = np.concatenate([side, bottom, top])
    vn = np.concatenate([ring, [[0, 0, -1.0], [0, 0, 1.0]]])
    fn = np.concatenate(
        [
            np.stack([i, j, j], 1),
            np.stack([i, j, i], 1),
            np.full((n, 3), n),
            np.full((n, 3), n + 1),
        ]
    )
    return Mesh(v, f, vn, fn)


def ellipsoid(radii: np.ndarray, around: int, rings: int) -> Mesh:
    """A UV-sphere ellipsoid of semi-axes `radii`, centred on the origin, smooth-shaded."""
    a, b, c = (float(r) for r in radii)
    theta = np.linspace(0, math.pi, rings + 1)  # pole to pole
    phi = np.linspace(0, 2 * math.pi, around, endpoint=False)
    th, ph = np.meshgrid(theta, phi, indexing="ij")
    unit = np.stack([np.sin(th) * np.cos(ph), np.sin(th) * np.sin(ph), np.cos(th)], -1)
    v = (unit * [a, b, c]).reshape(-1, 3)
    normal = (unit / [a, b, c]).reshape(-1, 3)
    normal /= np.linalg.norm(normal, axis=1, keepdims=True)
    idx = np.arange((rings + 1) * around).reshape(rings + 1, around)
    nxt = np.roll(idx, -1, axis=1)
    q0, q1 = idx[:-1].ravel(), nxt[:-1].ravel()
    q2, q3 = nxt[1:].ravel(), idx[1:].ravel()
    # theta grows downward, so (q0, q3, q2) runs counter-clockwise seen from outside
    f = np.concatenate([np.stack([q0, q3, q2], 1), np.stack([q0, q2, q1], 1)])
    area = np.linalg.norm(np.cross(v[f[:, 1]] - v[f[:, 0]], v[f[:, 2]] - v[f[:, 0]]), axis=1)
    f = f[area > 0]  # drop the slivers at the poles
    return Mesh(v, f, normal, f.copy())


def quad(x0: float, x1: float, y0: float, y1: float, z: float, uv_repeat=(1.0, 1.0)) -> Mesh:
    """A flat, upward-facing rectangle with texture coordinates 0..repeat (MuJoCo's v)."""
    v = np.array([[x0, y0, z], [x1, y0, z], [x1, y1, z], [x0, y1, z]], float)
    ru, rv = uv_repeat
    vt = np.array([[0, 0], [ru, 0], [ru, rv], [0, rv]], float)
    f = np.array([[0, 1, 2], [0, 2, 3]])
    return Mesh(v, f, np.array([[0.0, 0.0, 1.0]]), np.zeros_like(f), vt, f.copy())


def _block(prefix: str, rows: np.ndarray, decimals: int) -> str:
    buf = io.StringIO()
    np.savetxt(buf, rows, fmt=f"{prefix} " + " ".join([f"%.{decimals}f"] * rows.shape[1]))
    return buf.getvalue()


def obj_text(mesh: Mesh, decimals: int) -> str:
    """Wavefront OBJ text of `mesh`; texture v is flipped to OBJ's bottom-row origin."""
    parts = [_block("v", mesh.v, decimals), _block("vn", mesh.vn, 6)]
    one = 1  # OBJ indices start at 1
    if mesh.vt is not None:
        vt = mesh.vt.copy()
        vt[:, 1] = 1.0 - vt[:, 1]
        parts.append(_block("vt", vt, 6))
        corners = np.stack([mesh.f + one, mesh.ft + one, mesh.fn + one], -1).reshape(-1, 9)
        fmt = "f " + " ".join(["%d/%d/%d"] * 3)
    else:
        corners = np.stack([mesh.f + one, mesh.fn + one], -1).reshape(-1, 6)
        fmt = "f " + " ".join(["%d//%d"] * 3)
    buf = io.StringIO()
    np.savetxt(buf, corners, fmt=fmt)
    parts.append(buf.getvalue())
    return "".join(parts)


def write_obj(path: Path, mesh: Mesh, decimals: int) -> int:
    """Write `mesh` as OBJ; returns the bytes written."""
    path.parent.mkdir(parents=True, exist_ok=True)
    text = obj_text(mesh, decimals)
    path.write_text(text)
    return len(text)


def read_obj(path: Path) -> Mesh:
    """Read back what `write_obj` wrote (texture v in MuJoCo's convention again)."""
    v, vt, vn, f, ft, fn = [], [], [], [], [], []
    for line in Path(path).read_text().splitlines():
        tag, *rest = line.split()
        if tag == "v":
            v.append([float(x) for x in rest])
        elif tag == "vt":
            vt.append([float(rest[0]), 1.0 - float(rest[1])])
        elif tag == "vn":
            vn.append([float(x) for x in rest])
        elif tag == "f":
            idx = [c.split("/") for c in rest]
            f.append([int(c[0]) - 1 for c in idx])
            if idx[0][1]:
                ft.append([int(c[1]) - 1 for c in idx])
            fn.append([int(c[2]) - 1 for c in idx])
    return Mesh(
        np.array(v),
        np.array(f),
        np.array(vn),
        np.array(fn),
        np.array(vt) if vt else None,
        np.array(ft) if ft else None,
    )
