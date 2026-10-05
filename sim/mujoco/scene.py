"""Assemble the MuJoCo scene for one road: surface tiles, kerbs, shoulders, sky, sun,
haze, poles, a wall, signs, and the vehicle carrying the camera.

The camera is the design camera from the `sim:` block of configs/project.yaml: 1.3 m
high, pitched down 10 degrees, 1.2 rad horizontal field of view, 1280x720. MuJoCo takes
a vertical field of view, so `fovy = 2 atan(tan(hfov / 2) h / w)`, which gives the same
focal length as core.geometry's `f = (w / 2) / tan(hfov / 2)` (tests/test_mujoco_camera.py).
"""

from __future__ import annotations

import math

import mujoco
import numpy as np
import yaml

from certain_road.core.paths import repo_root
from sim.mujoco.road import Road
from sim.mujoco.surface import Baker


def design_camera() -> dict:
    s = yaml.safe_load((repo_root() / "configs/project.yaml").read_text())["sim"]
    w, h, hfov = s["cam_w"], s["cam_h"], s["cam_fov_rad"]
    return {
        "w": w,
        "h": h,
        "hfov": hfov,
        "height": s["cam_height_m"],
        "pitch": math.radians(s["cam_pitch_deg"]),
        "fovy_deg": math.degrees(2 * math.atan(math.tan(hfov / 2) * h / w)),
        "f": (w / 2) / math.tan(hfov / 2),
        "speed_mps": s["speed_kmh"] / 3.6,
    }


def camera_quat(pitch: float, roll: float = 0.0) -> list[float]:
    """Camera looking along +x (road forward), pitched down, image right = -y."""
    cp, sp = math.cos(pitch), math.sin(pitch)
    xc = np.array([0.0, -1.0, 0.0])
    yc = np.array([sp, 0.0, cp])
    zc = np.cross(xc, yc)
    if roll:
        c, s = math.cos(roll), math.sin(roll)
        xc, yc = c * xc + s * yc, -s * xc + c * yc
    r = np.stack([xc, yc, zc], axis=1)
    q = np.zeros(4)
    mujoco.mju_mat2Quat(q, r.flatten())
    return q.tolist()


def _tex(spec, name, img: np.ndarray):
    t = spec.add_texture(
        name=name,
        type=mujoco.mjtTexture.mjTEXTURE_2D,
        width=img.shape[1],
        height=img.shape[0],
        nchannel=3,
    )
    t.data = np.ascontiguousarray(img).tobytes()
    m = spec.add_material(name=name, specular=0.05, shininess=0.1)
    m.textures[mujoco.mjtTextureRole.mjTEXROLE_RGB] = name
    return name


def _quad(spec, name, x0, x1, y0, y1, z=0.0):
    mesh = spec.add_mesh(name=name)
    mesh.uservert = [x0, y0, z, x1, y0, z, x1, y1, z, x0, y1, z]
    mesh.userface = [0, 1, 2, 0, 2, 3]
    mesh.usertexcoord = [0, 0, 1, 0, 1, 1, 0, 1]
    mesh.inertia = mujoco.mjtMeshInertia.mjMESH_INERTIA_SHELL
    return name


def _noise_tex(rng, h, w, base, amp, blur):
    n = rng.normal(0, 1, (h, w, 1)).astype(np.float32)
    import cv2

    n = cv2.GaussianBlur(n, (0, 0), blur)[..., None] if blur else n
    n = n / (n.std() + 1e-6)
    fine = rng.normal(0, 0.5, (h, w, 1))
    img = np.array(base)[None, None, :] * (1 + amp * n + 0.5 * amp * fine)
    return (np.clip(img, 0, 1) * 255).astype(np.uint8)


def build(road: Road, cfg: dict) -> tuple[mujoco.MjModel, dict]:
    sc, rc = cfg["scene"], cfg["road"]
    cam = design_camera()
    spec = mujoco.MjSpec()
    ss = cfg["camera_effects"]["supersample"]
    spec.visual.global_.offwidth, spec.visual.global_.offheight = cam["w"] * ss, cam["h"] * ss
    spec.visual.quality.shadowsize = sc["shadow_size"]
    spec.stat.extent = 100.0
    spec.stat.center = [road.length_m / 2, 0, 0]
    spec.visual.map.shadowclip = sc["shadow_box_m"] / spec.stat.extent
    spec.visual.map.fogstart = sc["haze"]["start_m"] / spec.stat.extent
    spec.visual.map.fogend = sc["haze"]["end_m"] / spec.stat.extent
    spec.visual.map.zfar = 30.0
    spec.visual.rgba.fog = [*sc["haze"]["rgb"], 1]
    spec.visual.rgba.haze = [*sc["haze"]["rgb"], 1]
    spec.visual.headlight.ambient = [sc["ambient"]] * 3
    spec.visual.headlight.diffuse = [0.08] * 3
    spec.visual.headlight.specular = [0.0] * 3
    sky = spec.add_texture(
        name="sky",
        type=mujoco.mjtTexture.mjTEXTURE_SKYBOX,
        builtin=mujoco.mjtBuiltin.mjBUILTIN_GRADIENT,
        rgb1=sc["sky"]["top"],
        rgb2=sc["sky"]["horizon"],
        width=512,
        height=3072,
    )
    del sky
    rng = np.random.default_rng([road.seed, 23])
    w2 = road.lane_width_m
    baker = Baker(road, cfg)
    tm = cfg["surface"]["tile_m"]
    for k in range(baker.n_tiles):
        mat = _tex(spec, f"road{k}", baker.tile(k))
        spec.worldbody.add_geom(
            type=mujoco.mjtGeom.mjGEOM_MESH,
            meshname=_quad(spec, f"q{k}", k * tm, (k + 1) * tm, -w2, w2),
            material=mat,
            contype=0,
            conaffinity=0,
        )
    L = baker.n_tiles * tm
    kb = rc["kerb"]
    nstripe = int(L / kb["stripe_m"])
    for side in (-1, 1):
        yk = side * (w2 + kb["width_m"] / 2)
        for i in range(nstripe):
            shade = 0.86 if i % 2 == 0 else 0.12
            jitter = rng.uniform(-0.03, 0.03)
            spec.worldbody.add_geom(
                type=mujoco.mjtGeom.mjGEOM_BOX,
                pos=[(i + 0.5) * kb["stripe_m"], yk, kb["height_m"] / 2],
                size=[kb["stripe_m"] / 2 - 0.004, kb["width_m"] / 2, kb["height_m"] / 2],
                rgba=[shade + jitter, shade + jitter, shade * 0.97 + jitter, 1],
                contype=0,
                conaffinity=0,
            )
        y0 = side * (w2 + kb["width_m"])
        y1 = side * (w2 + kb["width_m"] + rc["shoulder_m"])
        sh = _tex(spec, f"shoulder{side}", _noise_tex(rng, 64, 2048, [0.55, 0.47, 0.38], 0.12, 1.5))
        spec.worldbody.add_geom(
            type=mujoco.mjtGeom.mjGEOM_MESH,
            meshname=_quad(spec, f"sq{side}", -20, L + 60, min(y0, y1), max(y0, y1), 0.005),
            material=sh,
            contype=0,
            conaffinity=0,
        )
    ground = _tex(spec, "ground", _noise_tex(rng, 256, 256, [0.52, 0.5, 0.38], 0.18, 2.0))
    gm = spec.materials[-1]
    gm.texrepeat = [60, 60]
    spec.worldbody.add_geom(
        type=mujoco.mjtGeom.mjGEOM_PLANE,
        pos=[L / 2, 0, -0.01],
        size=[L, 200, 1],
        material=ground,
        contype=0,
        conaffinity=0,
    )
    del gm
    # utility poles on the left verge, with a crossarm
    x = rng.uniform(5, 20)
    yp = w2 + kb["width_m"] + sc["pole_offset_m"]
    ph = sc["pole_height_m"]
    while x < L + 40:
        spec.worldbody.add_geom(
            type=mujoco.mjtGeom.mjGEOM_CYLINDER,
            pos=[x, yp, ph / 2],
            size=[0.13, ph / 2],
            rgba=[0.62, 0.61, 0.58, 1],
            contype=0,
            conaffinity=0,
        )
        spec.worldbody.add_geom(
            type=mujoco.mjtGeom.mjGEOM_BOX,
            pos=[x, yp - 0.4, ph - 0.5],
            size=[0.06, 0.9, 0.05],
            rgba=[0.3, 0.3, 0.3, 1],
            contype=0,
            conaffinity=0,
        )
        x += rng.uniform(*sc["pole_spacing_m"])
    # a compound wall along part of the right side
    wc = sc["wall"]
    wl = L * rng.uniform(*wc["length_frac"])
    wx = rng.uniform(0, L - wl)
    wall = _tex(spec, "wall", _noise_tex(rng, 64, 1024, [0.78, 0.72, 0.62], 0.08, 3.0))
    spec.worldbody.add_geom(
        type=mujoco.mjtGeom.mjGEOM_BOX,
        pos=[wx + wl / 2, -(w2 + wc["offset_m"]), wc["height_m"] / 2],
        size=[wl / 2, 0.12, wc["height_m"] / 2],
        material=wall,
        contype=0,
        conaffinity=0,
    )
    # signs: a blue board on two posts, left verge
    for _ in range(max(1, int(L / 1000 * sc["signs_per_km"]))):
        sx = rng.uniform(10, L)
        for dy in (-0.5, 0.5):
            spec.worldbody.add_geom(
                type=mujoco.mjtGeom.mjGEOM_CYLINDER,
                pos=[sx, yp + 0.6 + dy, 1.2],
                size=[0.035, 1.2],
                rgba=[0.55, 0.55, 0.55, 1],
                contype=0,
                conaffinity=0,
            )
        spec.worldbody.add_geom(
            type=mujoco.mjtGeom.mjGEOM_BOX,
            pos=[sx, yp + 0.6, 2.4],
            size=[0.03, 0.75, 0.45],
            rgba=[0.1, 0.28, 0.6, 1],
            contype=0,
            conaffinity=0,
        )
    # the vehicle: camera and the sun travel with it, so the shadow box stays on the view
    veh = spec.worldbody.add_body(name="vehicle", mocap=True, pos=[0, road.drive_lane_y, 0])
    veh.add_camera(
        name="cam", pos=[0, 0, cam["height"]], quat=camera_quat(cam["pitch"]), fovy=cam["fovy_deg"]
    )
    d = np.array(sc["sun_dir"], float)
    d /= np.linalg.norm(d)
    veh.add_light(
        name="sun",
        type=mujoco.mjtLightType.mjLIGHT_DIRECTIONAL,
        castshadow=1,
        pos=(15 - 30 * d).tolist(),
        dir=d.tolist(),
        diffuse=[sc["sun_diffuse"]] * 3,
        specular=[0.05] * 3,
        ambient=[0.0] * 3,
    )
    return spec.compile(), cam
